"""OCR.Space bridge for automatic AJPA PES6 league results.

Final flow:
Discord result photos -> OCR.Space -> AJPA structural/roster validation ->
official match + standings/scorers/app -> configured GES/results-to-load channel.

If OCR.Space cannot safely close a FINAL result or all scorers, the original
Discord evidence goes to Staff. Players are never asked to recreate a photo
after leaving the match. A clear halftime/partial screen simply waits for final.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request

import discord
from PIL import Image, ImageOps

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_local_ocr_patch as local
import league_result_evidence_patch as evidence
import league_validation_admin_review_patch as strict
import league_ges_result_queue_patch as ges
import pes_username_link_patch as pes_links

try:
    import league_ges_scorer_details_patch  # noqa: F401
except Exception as exc:
    print(f"WARNING AJPA OCRSPACE GES DETAIL: {type(exc).__name__}: {exc}")

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

API_URL = (os.getenv("OCR_SPACE_API_URL") or "https://api.ocr.space/parse/image").strip()
PRIMARY_ENGINE = str(os.getenv("AJAP_OCRSPACE_ENGINE") or "2").strip()
FALLBACK_ENGINE = str(os.getenv("AJAP_OCRSPACE_FALLBACK_ENGINE") or "3").strip()
MIN_CONF = float(os.getenv("AJAP_OCRSPACE_RESULT_CONFIDENCE") or league.MIN_CONF)
MAX_IMAGES = 4
MAX_DISCORD_IMAGE_BYTES = 8 * 1024 * 1024
# OCR.Space free tier accepts files up to 1 MB. Keep margin for form/base64 overhead.
OCRSPACE_TARGET_BYTES = 900 * 1024

_IMAGE_MIMES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/tiff",
}


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
    mime = str(getattr(att, "content_type", "") or "").split(";", 1)[0].strip().casefold()
    if mime in _IMAGE_MIMES:
        return True
    guessed = mimetypes.guess_type(str(getattr(att, "filename", "") or ""))[0] or ""
    return guessed.casefold() in _IMAGE_MIMES


async def _read_images(message):
    images, hashes = [], []
    for att in list(getattr(message, "attachments", None) or [])[:MAX_IMAGES]:
        if not _is_image(att):
            continue
        size = int(getattr(att, "size", 0) or 0)
        if size and size > MAX_DISCORD_IMAGE_BYTES:
            continue
        data = await att.read()
        if not data or len(data) > MAX_DISCORD_IMAGE_BYTES:
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in hashes:
            continue
        mime = str(getattr(att, "content_type", "") or "").split(";", 1)[0].strip().casefold()
        if mime not in _IMAGE_MIMES:
            mime = mimetypes.guess_type(str(getattr(att, "filename", "") or ""))[0] or "image/jpeg"
        images.append((data, mime.casefold()))
        hashes.append(digest)
    return images, hashes


def _compress_for_free_api(data: bytes):
    """Return JPEG bytes under OCR.Space free 1 MB file limit plus dimensions."""
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image).convert("RGB")

    # Preserve PES UI detail while avoiding huge phone-camera files.
    max_side = max(image.size)
    if max_side > 1920:
        ratio = 1920.0 / float(max_side)
        image = image.resize(
            (max(1, int(image.width * ratio)), max(1, int(image.height * ratio))),
            Image.Resampling.LANCZOS,
        )

    work = image
    for shrink_round in range(4):
        for quality in (90, 84, 78, 72, 66, 60):
            out = io.BytesIO()
            work.save(out, "JPEG", quality=quality, optimize=True)
            blob = out.getvalue()
            if len(blob) <= OCRSPACE_TARGET_BYTES:
                return blob, work.width, work.height
        if shrink_round < 3:
            work = work.resize(
                (max(1, int(work.width * 0.84)), max(1, int(work.height * 0.84))),
                Image.Resampling.LANCZOS,
            )

    raise RuntimeError("La foto no pudo reducirse por debajo del límite gratuito de OCR.Space")


def _overlay_rows(result: dict, width: int, height: int, engine: str):
    overlay = result.get("TextOverlay") if isinstance(result, dict) else None
    lines = overlay.get("Lines") if isinstance(overlay, dict) else None
    rows = []
    base_conf = 0.92 if str(engine) == "2" else 0.89

    if isinstance(lines, list):
        for line in lines:
            words = line.get("Words") if isinstance(line, dict) else None
            if not isinstance(words, list) or not words:
                continue

            clean_words = []
            for word in words:
                if not isinstance(word, dict):
                    continue
                text = str(word.get("WordText") or "").strip()
                if not text:
                    continue
                try:
                    left = float(word.get("Left") or 0)
                    top = float(word.get("Top") or 0)
                    ww = float(word.get("Width") or 0)
                    hh = float(word.get("Height") or 0)
                except (TypeError, ValueError):
                    continue
                clean_words.append((text, left, top, ww, hh))

                # Individual word boxes are useful for the two standalone score
                # digits and for scorer minute columns.
                rows.append(
                    {
                        "text": text,
                        "conf": base_conf,
                        "x": left + ww / 2.0,
                        "y": top + hh / 2.0,
                        "w": float(width),
                        "h": float(height),
                        "box": None,
                    }
                )

            if not clean_words:
                continue

            text = " ".join(item[0] for item in clean_words).strip()
            left = min(item[1] for item in clean_words)
            top = min(item[2] for item in clean_words)
            right = max(item[1] + item[3] for item in clean_words)
            bottom = max(item[2] + item[4] for item in clean_words)
            rows.append(
                {
                    "text": text,
                    "conf": base_conf,
                    "x": (left + right) / 2.0,
                    "y": (top + bottom) / 2.0,
                    "w": float(width),
                    "h": float(height),
                    "box": None,
                }
            )

    return rows


def _ocrspace_request(data: bytes, engine: str):
    api_key = (os.getenv("OCR_SPACE_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Falta OCR_SPACE_API_KEY")

    blob, width, height = _compress_for_free_api(data)
    form = {
        "base64Image": "data:image/jpeg;base64," + base64.b64encode(blob).decode("ascii"),
        "language": "auto",
        "isOverlayRequired": "true",
        "detectOrientation": "true",
        "scale": "true",
        "isTable": "true",
        "OCREngine": str(engine),
    }
    body = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "apikey": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"OCR.Space HTTP {exc.code}: {detail}") from exc

    if bool(payload.get("IsErroredOnProcessing")):
        raise RuntimeError(
            "OCR.Space: "
            + str(payload.get("ErrorMessage") or payload.get("ErrorDetails") or "error de procesamiento")[:500]
        )

    parsed = payload.get("ParsedResults")
    if not isinstance(parsed, list) or not parsed:
        raise RuntimeError("OCR.Space no devolvió resultados")

    pages = []
    for result in parsed:
        try:
            exit_code = int(result.get("FileParseExitCode"))
        except Exception:
            exit_code = 0
        if exit_code != 1:
            continue
        rows = _overlay_rows(result, width, height, engine)
        if rows:
            pages.append(rows)

    if not pages:
        raise RuntimeError("OCR.Space no devolvió texto posicionado")
    return pages


def _ocrspace_all_items(images, engine: str):
    pages = []
    errors = []
    for data, _mime in images:
        try:
            pages.extend(_ocrspace_request(data, engine))
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    if pages:
        return pages
    raise RuntimeError(" | ".join(errors) if errors else "OCR.Space no pudo leer las imágenes")


def _payload_with_engine(images, engine: str, guild_id: int | None):
    # Use the already hardened PES6 parser (teams, score, username aliases and
    # scorer table/roster validation); only the OCR engine changes.
    original = local._all_items
    local._all_items = lambda imgs: _ocrspace_all_items(imgs, engine)
    token = None
    try:
        try:
            token = pes_links._RESULT_GUILD_ID.set(int(guild_id)) if guild_id is not None else None
        except Exception:
            token = None
        payload = local._local_payload(images)
    finally:
        local._all_items = original
        if token is not None:
            try:
                pes_links._RESULT_GUILD_ID.reset(token)
            except Exception:
                pass

    payload = dict(payload or {})
    payload["source_kind"] = "ocrspace"
    payload["ocr_engine"] = str(engine)
    payload["notes"] = f"OCR.Space Engine {engine}"
    return payload


def _payload_strength(payload):
    if not isinstance(payload, dict):
        return (0, 0.0, 0)
    score_ok = 1 if league.parsed_score(payload) else 0
    try:
        conf = float(payload.get("result_confidence") or payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    scorer_goals = 0
    for item in payload.get("scorers") or []:
        if isinstance(item, dict):
            try:
                scorer_goals += int(item.get("goals") or 0)
            except (TypeError, ValueError):
                pass
    return score_ok, conf, scorer_goals


async def _analyze(images, guild_id=None):
    primary = await asyncio.to_thread(_payload_with_engine, images, PRIMARY_ENGINE, guild_id)
    state = str(primary.get("match_state") or "unknown").casefold()
    strength = _payload_strength(primary)

    # Do not burn Engine 3 quota on a clear primary read. Use it only for weak/
    # unreadable final evidence; Engine 3 is better with stylized fonts.
    if (
        FALLBACK_ENGINE
        and FALLBACK_ENGINE != PRIMARY_ENGINE
        and (strength[0] == 0 or strength[1] < MIN_CONF or state == "unknown")
    ):
        try:
            fallback = await asyncio.to_thread(
                _payload_with_engine, images, FALLBACK_ENGINE, guild_id
            )
            if _payload_strength(fallback) > strength:
                return fallback
        except Exception as exc:
            print(f"WARNING AJPA OCRSPACE ENGINE {FALLBACK_ENGINE}: {type(exc).__name__}: {exc}")
    return primary


def _score(payload):
    return league.parsed_score(payload)


def _roster_rows(runtime, guild_id):
    out = []
    for row in league.roster(runtime, int(guild_id)):
        try:
            name = str(row["name"] or "").strip()
            club = league.canonical_team(row["club"])
        except Exception:
            continue
        if name and club:
            out.append((name, club, league.norm(name)))
    return out


def _clean_scorers(runtime, guild_id, payload, score):
    home, away, hg, ag = score
    roster = _roster_rows(runtime, guild_id)
    roster_map = {(key, club): name for name, club, key in roster}
    by_name = {}
    for name, club, key in roster:
        by_name.setdefault(key, []).append((name, club))

    consolidated = {}
    for item in payload.get("scorers") or []:
        if not isinstance(item, dict):
            continue
        raw_name = league.norm(item.get("player"))
        raw_team = league.canonical_team(item.get("team"))
        if not raw_name:
            continue

        resolved = None
        if raw_team in {home, away}:
            exact = roster_map.get((raw_name, raw_team))
            if exact:
                resolved = (exact, raw_team)
        if resolved is None:
            candidates = [pair for pair in by_name.get(raw_name, []) if pair[1] in {home, away}]
            if len(candidates) == 1:
                resolved = candidates[0]
        if resolved is None:
            continue

        name, club = resolved
        try:
            goals = int(item.get("goals", 1))
        except (TypeError, ValueError):
            continue
        if not (1 <= goals <= 20):
            continue
        key = (league.norm(name), club)
        if key not in consolidated:
            consolidated[key] = [name, club, 0]
        consolidated[key][2] = max(consolidated[key][2], goals)

    limits = {home: int(hg), away: int(ag)}
    totals = {home: 0, away: 0}
    for _, club, goals in consolidated.values():
        totals[club] += int(goals)
    if any(totals[team] > limits[team] for team in (home, away)):
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
    return club is None or club in {home, away}


def _scorer_totals(home, away, scorers):
    totals = {home: 0, away: 0}
    for item in scorers:
        club = item.get("team")
        if club in totals:
            totals[club] += int(item.get("goals") or 0)
    return totals


def _missing_scorer_reason(home, away, hg, ag, scorers):
    totals = _scorer_totals(home, away, scorers)
    missing = []
    for team, expected in ((home, int(hg)), (away, int(ag))):
        diff = expected - totals.get(team, 0)
        if diff > 0:
            missing.append(f"{team}: faltan {diff}")
        elif diff < 0:
            missing.append(f"{team}: sobran {-diff}")
    if not missing:
        return None
    return (
        f"OCR.Space leyó {home} {hg}-{ag} {away}, pero no pudo cerrar todos "
        f"los goleadores contra las plantillas ({'; '.join(missing)})."
    )


def _format_scorers(home, away, hg, ag, scorers):
    groups = {home: [], away: []}
    for item in scorers:
        club = item["team"]
        goals = int(item["goals"])
        label = str(item["player"])
        if goals > 1:
            label += f" x{goals}"
        groups[club].append(label)
    lines = []
    for team, expected in ((home, hg), (away, ag)):
        if int(expected) <= 0:
            continue
        lines.append(f"⚽ **{team}:** {', '.join(groups[team])}")
    return "\n".join(lines) if lines else "⚽ Sin goleadores para registrar."


async def _safe_reply(message, text):
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


async def _send_staff_review(message, reason, hashes=None, payload=None):
    saved = dict(payload or {})
    saved.setdefault("kind", "unknown")
    saved.setdefault("match_state", "unknown")
    saved.setdefault("home_team", "")
    saved.setdefault("away_team", "")
    saved.setdefault("home_goals", None)
    saved.setdefault("away_goals", None)
    saved.setdefault("scorers", [])
    saved.setdefault("confidence", 0.0)
    saved["source_kind"] = "ocrspace"
    old_notes = str(saved.get("notes") or "").strip()
    saved["notes"] = f"{old_notes} | {reason}".strip(" |")

    try:
        try:
            return await strict._send_admin_review(
                message, reason, hashes, payload=saved
            )
        except TypeError as exc:
            if "payload" not in str(exc):
                raise
            return await strict._send_admin_review(message, reason, hashes)
    except Exception as exc:
        print(
            f"WARNING AJPA OCRSPACE STAFF source={getattr(message, 'id', '?')}: "
            f"{type(exc).__name__}: {exc}"
        )
        await _safe_reply(
            message,
            "⚠️ El resultado necesita revisión de Staff, pero no pude crear la tarjeta "
            "automática. Conservá esta foto en el canal y avisale a un administrador.",
        )
        return False


async def ocrspace_result_handle(runtime, bot, message):
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

    try:
        images, hashes = await _read_images(message)
    except Exception as exc:
        await _send_staff_review(
            message,
            f"No pude recuperar la foto original: {type(exc).__name__}: {str(exc)[:300]}",
        )
        return

    if not images:
        await _send_staff_review(message, "No encontré una imagen válida para procesar.", hashes)
        return

    try:
        payload = await _analyze(images, message.guild.id)
    except Exception as exc:
        print(f"WARNING AJPA OCRSPACE RESULT: {type(exc).__name__}: {exc}")
        await _send_staff_review(
            message,
            f"OCR.Space no pudo procesar la captura: {type(exc).__name__}: {str(exc)[:350]}",
            hashes,
        )
        return

    try:
        confidence = float(payload.get("result_confidence") or payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    state = str(payload.get("match_state") or "unknown").casefold()
    score = _score(payload)

    if state == "partial":
        await _safe_reply(
            message,
            "🟡 Detecté **primer tiempo/resultado parcial**. No cargué puntos. "
            "Cuando termine el partido, mandá la foto final.",
        )
        return

    if not score or state != "final" or confidence < MIN_CONF:
        reason = (
            "OCR.Space no pudo confirmar con suficiente seguridad los dos equipos "
            f"y el marcador FINAL (estado={state}, confianza={confidence:.0%})."
        )
        await _send_staff_review(message, reason, hashes, payload)
        return

    home, away, hg, ag = score
    if not _soft_reporter_check(runtime, message, home, away):
        await _send_staff_review(
            message,
            f"OCR.Space leyó {home} {hg}-{ag} {away}, pero el club vinculado al "
            "autor no coincide con ninguno de los dos equipos.",
            hashes,
            payload,
        )
        return

    scorers = _clean_scorers(runtime, message.guild.id, payload, score)
    scorer_issue = _missing_scorer_reason(home, away, hg, ag, scorers)
    if scorer_issue:
        await _send_staff_review(message, scorer_issue, hashes, payload)
        return

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
            "source_kind": "ocrspace",
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
            "OCRSPACE_VALIDADO",
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
            await _safe_reply(
                message,
                "ℹ️ El cruce ya tiene un resultado oficial cargado. "
                "No dupliqué el partido ni los puntos.",
            )
            return
        if not ok:
            raise RuntimeError(f"No se pudo persistir resultado: {result_state}")
    except Exception as exc:
        print(f"WARNING AJPA OCRSPACE PERSIST: {type(exc).__name__}: {exc}")
        await _send_staff_review(
            message,
            f"OCR.Space leyó {home} {hg}-{ag} {away}, pero falló la carga automática "
            f"antes de confirmar el partido: {type(exc).__name__}: {str(exc)[:300]}",
            hashes,
            clean_payload,
        )
        return

    try:
        await league.refresh(runtime, bot, message.guild.id)
    except Exception as exc:
        print(f"WARNING AJPA OCRSPACE REFRESH: {type(exc).__name__}: {exc}")

    ges_sent = False
    try:
        await ges._send(runtime, message.guild.id, row, home, away, hg, ag)
        queued = ges._find(runtime, message.guild.id, source=message.id)
        ges_sent = bool(queued and queued["ges_message_id"])
    except Exception as exc:
        print(f"WARNING AJPA OCRSPACE GES: {type(exc).__name__}: {exc}")

    await _react(message, "✅")
    scorer_text = _format_scorers(home, away, hg, ag, scorers)
    ges_line = (
        "📋 **Resultados para cargar:** enviado al canal configurado."
        if ges_sent
        else "⚠️ **Resultados para cargar:** el partido quedó oficial, pero no pude "
             "confirmar la publicación de la tarjeta."
    )
    await _safe_reply(
        message,
        "✅ **RESULTADO CARGADO AUTOMÁTICAMENTE**\n"
        f"## {home} {hg} - {ag} {away}\n"
        f"{scorer_text}\n\n"
        "📲 **App actualizada:** resultado + puntos/tabla + goleadores.\n"
        f"{ges_line}",
    )


def _install_handlers():
    league.handle = ocrspace_result_handle
    if feedback is not None:
        feedback._feedback_handle = ocrspace_result_handle
    evidence.evidence_handle = ocrspace_result_handle
    if rescue is not None:
        rescue.reliable_evidence_handle = ocrspace_result_handle

    if pending_reprocess is not None:
        def _disabled_pending_reprocess(runtime, bot):
            bot._ajap_pending_review_reprocess_listener = True
            print("AJPA Liga: relectura histórica con lector viejo DESACTIVADA")
        pending_reprocess.install_pending_review_reprocess = _disabled_pending_reprocess


async def _keep_ocrspace_on_ready():
    _install_handlers()
    print(
        f"AJPA Liga: OCR.Space ACTIVO | Engine {PRIMARY_ENGINE} "
        f"| fallback Engine {FALLBACK_ENGINE or 'off'}"
    )


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    _install_handlers()

    if getattr(runtime, "_ajap_ocrspace_result_bridge", False):
        return
    if not getattr(bot, "_ajap_ocrspace_result_ready_listener", False):
        bot.add_listener(_keep_ocrspace_on_ready, "on_ready")
        bot._ajap_ocrspace_result_ready_listener = True
    runtime._ajap_ocrspace_result_bridge = True


_install_handlers()

_PREVIOUS = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _PREVIOUS(runtime, bot)
    _install(runtime, bot)
    _install_handlers()


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_ocrspace_result_wrapper", False):
    _apply._ajap_ocrspace_result_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply

print(
    f"AJPA Liga: puente OCR.Space cargado | Engine {PRIMARY_ENGINE} "
    f"| fallback {FALLBACK_ENGINE or 'off'} | Staff ante cualquier final incompleto"
)
