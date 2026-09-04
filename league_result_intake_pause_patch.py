"""Gemini Vision bridge for automatic AJPA league results.

Flow:
Discord screenshots -> Gemini -> strict AJPA validation -> official DB ->
app standings/scorers + configured GES results queue.

This module is imported LAST. It replaces the old OCR/OpenAI result readers only;
the rest of the league/market bot remains untouched.
"""
from __future__ import annotations

import asyncio
import base64
import difflib
import hashlib
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_result_evidence_patch as evidence
import league_ges_result_queue_patch as ges
# Reuse the existing Staff/GES card renderer so the result-to-load channel also
# receives the recognized scorer details.
try:
    import league_ges_scorer_details_patch  # noqa: F401
except Exception as exc:
    print(f"WARNING AJPA GEMINI: no se pudo cargar detalle GES: {type(exc).__name__}: {exc}")

try:
    import league_result_feedback_patch as feedback
except Exception:
    feedback = None

try:
    import league_runtime_result_rescue_patch as rescue
except Exception:
    rescue = None

try:
    import league_pending_review_reprocess_patch as pending_reprocess
except Exception:
    pending_reprocess = None


APP = None
BOT = None

MODEL = (os.getenv("AJAP_GEMINI_RESULT_MODEL") or "gemini-3.5-flash").strip()
MIN_CONF = float(os.getenv("AJAP_GEMINI_RESULT_CONFIDENCE", "0.78"))
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024

_IMAGE_MIMES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/tiff",
    "image/heic",
    "image/heif",
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": ["result", "scorers", "both", "unknown"],
        },
        "match_state": {
            "type": "string",
            "enum": ["final", "partial", "unknown"],
        },
        "home_team": {"type": "string"},
        "away_team": {"type": "string"},
        "home_goals": {"type": "integer", "minimum": -1, "maximum": 20},
        "away_goals": {"type": "integer", "minimum": -1, "maximum": 20},
        "scorers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "player": {"type": "string"},
                    "team": {"type": "string"},
                    "goals": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["player", "team", "goals"],
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "notes": {"type": "string"},
    },
    "required": [
        "kind",
        "match_state",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "scorers",
        "confidence",
        "notes",
    ],
}


def _norm(value):
    return league.norm(value)


def _configured_intake(runtime, guild_id: int):
    try:
        conn = league.db(runtime, int(guild_id), must_exist=True)
    except Exception:
        conn = None
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT intake_channel_id FROM league_config WHERE guild_id=? LIMIT 1",
            (int(guild_id),),
        ).fetchone()
        return int(row["intake_channel_id"]) if row and row["intake_channel_id"] else None
    finally:
        conn.close()


def _is_image(att) -> bool:
    mime = (
        str(getattr(att, "content_type", "") or "")
        .split(";", 1)[0]
        .strip()
        .casefold()
    )
    if mime in _IMAGE_MIMES:
        return True
    guessed = mimetypes.guess_type(str(getattr(att, "filename", "") or ""))[0] or ""
    return guessed.casefold() in _IMAGE_MIMES


async def _read_images(message):
    images = []
    hashes = []
    total = 0
    for att in list(getattr(message, "attachments", None) or [])[:MAX_IMAGES]:
        if not _is_image(att):
            continue
        size = int(getattr(att, "size", 0) or 0)
        if size and size > MAX_IMAGE_BYTES:
            continue

        data = await att.read()
        if not data or len(data) > MAX_IMAGE_BYTES:
            continue
        if total + len(data) > MAX_TOTAL_BYTES:
            break

        mime = (
            str(getattr(att, "content_type", "") or "")
            .split(";", 1)[0]
            .strip()
            .casefold()
        )
        if mime not in _IMAGE_MIMES:
            mime = (mimetypes.guess_type(str(getattr(att, "filename", "") or ""))[0] or "image/jpeg").casefold()
        if mime not in _IMAGE_MIMES:
            mime = "image/jpeg"

        digest = hashlib.sha256(data).hexdigest()
        if digest in hashes:
            continue
        images.append((data, mime))
        hashes.append(digest)
        total += len(data)
    return images, hashes


def _aliases_for_prompt():
    pairs = []
    for alias, club in sorted(getattr(league, "ALIASES", {}).items()):
        if alias and club and _norm(alias) != _norm(club):
            pairs.append(f"{alias} -> {club}")
    return ", ".join(pairs[:100])


def _prompt():
    teams = ", ".join(str(t) for t in league.TEAMS)
    aliases = _aliases_for_prompt()
    return f"""Leé estas capturas como evidencia de UN MISMO partido de la Liga AJPA de PES 6.

Objetivo: extraer el resultado final y, cuando aparezcan, los goleadores. No inventes nada.

Equipos oficiales AJPA:
{teams}

Alias/nombres sin licencia de PES 6 que pueden aparecer:
{aliases}

Reglas:
- `home_team` y `away_team` deben devolverse con el nombre OFICIAL AJPA cuando puedas resolverlo.
- `home_goals` y `away_goals` son el marcador TOTAL del partido. Si no se puede leer, usá -1.
- `match_state=final` cuando la captura muestre claramente una pantalla final/post-partido. En PES 6, una pantalla de resultado con desglose 1er/2do y opciones posteriores como "Terminar juego", "Jugar otro partido", "Pasar a Selec. de Equipo" o "Detalles del partido" cuenta como FINAL.
- `match_state=partial` si se ve primer tiempo/entretiempo o una pantalla inequívocamente parcial.
- `match_state=unknown` si hay marcador pero no hay evidencia suficiente para saber si terminó.
- `scorers` contiene SOLO nombres visibles como goleadores en las capturas. Consolidá repeticiones del mismo jugador usando `goals`.
- Asociá cada goleador con el equipo que corresponda. No uses conocimiento externo.
- La suma de goleadores identificados de un equipo puede ser menor al marcador si faltan nombres, pero nunca mayor.
- Si una captura muestra el marcador y otra la lista de goleadores, combiná ambas.
- No confundas Categoria, Puntos, minutos, chat, estadísticas u otros números con el marcador.
- `confidence` mide la confianza de la extracción completa.
"""


def _interaction_text(payload):
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        outputs = payload.get("output")
    if not isinstance(outputs, list):
        return ""

    parts = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        direct = item.get("text")
        if isinstance(direct, str):
            parts.append(direct)
        content = item.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
    return "\n".join(parts).strip()


def _gemini_sync(images):
    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Falta GEMINI_API_KEY")

    input_blocks = [{"type": "text", "text": _prompt()}]
    for data, mime in images:
        input_blocks.append(
            {
                "type": "image",
                "data": base64.b64encode(data).decode("ascii"),
                "mime_type": mime,
                "resolution": "high",
            }
        )

    body = json.dumps(
        {
            "model": MODEL,
            "input": input_blocks,
            "generation_config": {
                "thinking_level": "low",
                "max_output_tokens": 1200,
            },
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": _SCHEMA,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")

    last_error = None
    for attempt in range(2):
        req = urllib.request.Request(
            API_URL,
            data=body,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as res:
                payload = json.loads(res.read().decode("utf-8"))
            text = _interaction_text(payload)
            if not text:
                raise RuntimeError("Gemini no devolvió output_text")
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise RuntimeError("Gemini no devolvió un objeto JSON")
            return parsed
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:600]
            last_error = RuntimeError(f"Gemini HTTP {exc.code}: {detail}")
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt:
                raise last_error from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt:
                raise
        time.sleep(0.8)

    raise last_error or RuntimeError("Error desconocido de Gemini")


async def _analyze(images):
    return await asyncio.to_thread(_gemini_sync, images)


def _score(payload):
    if str(payload.get("kind") or "").casefold() not in {"result", "both"}:
        return None
    home = league.canonical_team(payload.get("home_team"))
    away = league.canonical_team(payload.get("away_team"))
    if not home or not away or home == away:
        return None
    try:
        hg = int(payload.get("home_goals"))
        ag = int(payload.get("away_goals"))
    except (TypeError, ValueError):
        return None
    if not (0 <= hg <= 20 and 0 <= ag <= 20):
        return None
    return home, away, hg, ag


def _roster_rows(runtime, guild_id):
    rows = league.roster(runtime, guild_id)
    out = []
    for row in rows:
        try:
            name = str(row["name"] or "").strip()
            club = league.canonical_team(row["club"])
        except Exception:
            continue
        if name and club:
            out.append((name, club, _norm(name)))
    return out


def _resolve_player(rows, raw_name, raw_team, allowed_teams):
    name_key = _norm(raw_name)
    if not name_key:
        return None

    requested_team = league.canonical_team(raw_team)
    pool = [row for row in rows if row[1] in allowed_teams]
    if requested_team in allowed_teams:
        team_pool = [row for row in pool if row[1] == requested_team]
        if team_pool:
            pool = team_pool

    exact = [row for row in pool if row[2] == name_key]
    if exact:
        return exact[0][0], exact[0][1]

    keys = [row[2] for row in pool]
    match = difflib.get_close_matches(name_key, keys, n=1, cutoff=0.84)
    if not match:
        return None
    for row in pool:
        if row[2] == match[0]:
            return row[0], row[1]
    return None


def _clean_scorers(runtime, guild_id, payload, score):
    home, away, hg, ag = score
    rows = _roster_rows(runtime, guild_id)
    consolidated = {}

    for item in payload.get("scorers") or []:
        if not isinstance(item, dict):
            continue
        resolved = _resolve_player(
            rows,
            item.get("player"),
            item.get("team"),
            {home, away},
        )
        if not resolved:
            continue
        name, club = resolved
        try:
            goals = int(item.get("goals", 1))
        except (TypeError, ValueError):
            continue
        if not (1 <= goals <= 20):
            continue
        key = (_norm(name), club)
        if key not in consolidated:
            consolidated[key] = [name, club, 0]
        consolidated[key][2] += goals

    limits = {home: hg, away: ag}
    team_totals = {home: 0, away: 0}
    for _, club, goals in consolidated.values():
        team_totals[club] += int(goals)

    # Never write an impossible scorer table. The result can still be official.
    if any(team_totals[team] > limits[team] for team in (home, away)):
        return []

    return [
        {"player": name, "team": club, "goals": int(goals)}
        for name, club, goals in consolidated.values()
    ]


def _soft_reporter_check(runtime, message, home, away):
    try:
        if isinstance(message.author, discord.Member) and message.author.guild_permissions.administrator:
            return True
    except Exception:
        pass
    try:
        club = evidence._club_for_user(runtime, message.guild.id, message.author.id)
    except Exception:
        club = None
    # No link -> do not block the automation. If a link exists, it must match.
    return club is None or club in {home, away}


def _format_scorers(home, away, hg, ag, scorers):
    groups = {home: [], away: []}
    totals = {home: 0, away: 0}
    for item in scorers:
        club = item["team"]
        goals = int(item["goals"])
        totals[club] += goals
        label = str(item["player"])
        if goals > 1:
            label += f" x{goals}"
        groups[club].append(label)

    lines = []
    for team, expected in ((home, hg), (away, ag)):
        if expected <= 0:
            continue
        names = ", ".join(groups[team]) if groups[team] else "sin identificar"
        missing = max(0, int(expected) - totals[team])
        if missing and groups[team]:
            names += f" • faltan {missing} sin identificar"
        lines.append(f"⚽ **{team}:** {names}")
    return "\n".join(lines) if lines else "⚽ Sin goleadores para registrar."


async def _reply(message, text):
    try:
        await message.reply(
            text,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except Exception:
        pass


async def _react(message, emoji):
    try:
        await message.add_reaction(emoji)
    except Exception:
        pass


async def gemini_result_handle(runtime, bot, message):
    if not getattr(message, "guild", None):
        return
    if getattr(getattr(message, "author", None), "bot", False):
        return

    intake = _configured_intake(runtime, message.guild.id)
    if not intake or int(getattr(getattr(message, "channel", None), "id", 0) or 0) != int(intake):
        return

    attachments = list(getattr(message, "attachments", None) or [])
    if not any(_is_image(att) for att in attachments):
        return

    await _react(message, "🔎")

    images, hashes = await _read_images(message)
    if not images:
        await _reply(message, "⚠️ No encontré una imagen válida para leer.")
        return

    try:
        payload = await _analyze(images)
    except Exception as exc:
        print(f"WARNING AJPA GEMINI RESULT: {type(exc).__name__}: {exc}")
        await _reply(
            message,
            "⚠️ No pude leer la captura ahora. Reintentá enviándola una vez más.",
        )
        return

    confidence = float(payload.get("confidence") or 0.0)
    state = str(payload.get("match_state") or "unknown").casefold()
    score = _score(payload)

    if state == "partial":
        await _reply(
            message,
            "🟡 Detecté que esta captura es de **primer tiempo/resultado parcial**. "
            "No cargué puntos. Mandá la captura final cuando termine.",
        )
        return

    if not score or state != "final" or confidence < MIN_CONF:
        await _reply(
            message,
            "⚠️ No pude confirmar **equipos + marcador final** con suficiente seguridad. "
            "No cargué nada. Reenviá una captura más clara de la pantalla final.",
        )
        return

    home, away, hg, ag = score
    if not _soft_reporter_check(runtime, message, home, away):
        await _reply(
            message,
            f"⚠️ Leí **{home} {hg}–{ag} {away}**, pero el club vinculado a quien envió "
            "la captura no coincide con ninguno de los dos equipos. No cargué el partido.",
        )
        return

    scorers = _clean_scorers(runtime, message.guild.id, payload, score)
    clean_payload = dict(payload)
    clean_payload.update(
        {
            "kind": "both" if scorers else "result",
            "match_state": "final",
            "home_team": home,
            "away_team": away,
            "home_goals": hg,
            "away_goals": ag,
            "scorers": scorers,
            "source_kind": "gemini",
            "confidence": confidence,
        }
    )

    try:
        evidence._stage(
            runtime,
            message,
            score,
            clean_payload,
            hashes,
            "GEMINI_VALIDADO",
        )
        row = evidence._row(
            runtime,
            message.guild.id,
            source_message_id=message.id,
        )
        if row is None:
            raise RuntimeError("No se pudo recuperar el resultado validado")

        ok, result_state, duplicate, scorer_count = evidence._persist_official(
            runtime,
            message.guild.id,
            row,
            include_scorers=True,
            status="FINAL_CARGADO",
        )

        if not ok and result_state == "DUPLICADO":
            await _reply(
                message,
                "ℹ️ El cruce ya tiene un resultado oficial cargado. "
                "No dupliqué el partido ni los puntos.",
            )
            return

        if not ok:
            raise RuntimeError(f"No se pudo persistir resultado: {result_state}")

        await league.refresh(runtime, bot, message.guild.id)

        ges_sent = False
        try:
            # Await the Staff/GES card here (instead of merely scheduling it) so
            # the success reply never claims delivery before Discord accepted it.
            await ges._send(runtime, message.guild.id, row, home, away, hg, ag)
            queued = ges._find(runtime, message.guild.id, source=message.id)
            ges_sent = bool(queued and queued["ges_message_id"])
        except Exception as ges_exc:
            print(f"WARNING AJPA GEMINI GES: {type(ges_exc).__name__}: {ges_exc}")
    except Exception as exc:
        print(f"WARNING AJPA GEMINI PERSIST: {type(exc).__name__}: {exc}")
        await _reply(
            message,
            "⚠️ Pude leer el resultado, pero falló la carga automática. "
            "No voy a decir que quedó cargado. Reintentá en unos segundos.",
        )
        return

    await _react(message, "✅")
    scorer_text = _format_scorers(home, away, hg, ag, scorers)
    ges_line = (
        "📋 **Resultados para cargar:** enviado al canal configurado."
        if ges_sent
        else "⚠️ **Resultados para cargar:** no hay un canal GES configurado o no pude publicar la tarjeta."
    )
    await _reply(
        message,
        (
            "✅ **RESULTADO CARGADO AUTOMÁTICAMENTE**\n"
            f"## {home} {hg} - {ag} {away}\n"
            f"{scorer_text}\n\n"
            "📲 **App actualizada:** resultado + puntos/tabla + goleadores.\n"
            f"{ges_line}"
        ),
    )


def _install_handlers():
    league.handle = gemini_result_handle
    if feedback is not None:
        feedback._feedback_handle = gemini_result_handle
    evidence.evidence_handle = gemini_result_handle
    if rescue is not None:
        rescue.reliable_evidence_handle = gemini_result_handle
    # The previous restart-time OCR recovery used the old local/OpenAI reader.
    # Keep historical review cards untouched; new captures are Gemini-only.
    if pending_reprocess is not None:
        def _disabled_pending_reprocess(runtime, bot):
            bot._ajap_pending_review_reprocess_listener = True
            print("AJPA Liga: relectura historica con OCR viejo DESACTIVADA")
        pending_reprocess.install_pending_review_reprocess = _disabled_pending_reprocess


async def _keep_gemini_on_ready():
    _install_handlers()
    print(f"AJPA Liga: Gemini result bridge ACTIVO | model={MODEL}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    _install_handlers()

    if getattr(runtime, "_ajap_gemini_result_bridge", False):
        return
    if not getattr(bot, "_ajap_gemini_result_ready_listener", False):
        bot.add_listener(_keep_gemini_on_ready, "on_ready")
        bot._ajap_gemini_result_ready_listener = True
    runtime._ajap_gemini_result_bridge = True


_install_handlers()

_PREVIOUS = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _PREVIOUS(runtime, bot)
    _install(runtime, bot)
    _install_handlers()


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_gemini_result_wrapper", False):
    _apply._ajap_gemini_result_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply

print(f"AJPA Liga: Gemini result bridge cargado | model={MODEL}")
