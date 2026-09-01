"""Goleadores escritos en reportes de Liga + reparación del 1-1 Everton/Villarreal.

La capa textual original evita mensajes con adjuntos. Este parche conserva el
flujo de capturas normal, pero cuando el mismo mensaje trae un marcador escrito
explícito permite interpretar el relato como declaración textual (con confirmación
rival) y extrae goleadores que el jugador escribió entre paréntesis.

También repara de forma idempotente el partido Everton 1-1 Villarreal ya cargado:
si a uno de los dos clubes le falta su único goleador, agrega los nombres
canónicos de las plantillas sin tocar el marcador.
"""

from __future__ import annotations

import difflib
import re

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_result_evidence_patch as evidence
import league_text_result_patch as text_result
import league_validation_admin_review_patch as strict


APP = None
BOT = None

_ORIGINAL_ANALYZE_TEXT = text_result._analyze_text
_ORIGINAL_PARSED_SCORERS = league.parsed_scorers


# ---------------------------------------------------------------------------
# Extraer goleadores escritos como "Equipo 2 (Jugador x2)".
# ---------------------------------------------------------------------------
def _labels_for_team(team: str):
    labels = {str(team)}
    for alias, canonical in league.ALIASES.items():
        if canonical == team:
            labels.add(str(alias))
    # Formas muy habituales que pueden aparecer aunque el nombre oficial lleve
    # aclaraciones largas.
    if team == "París Saint-Germain (PSG)":
        labels.update({"PSG", "Paris Saint-Germain", "Paris Saint Germain"})
    if team == "Atlético de Madrid":
        labels.update({"Atlético Madrid", "Atletico Madrid"})
    if team == "Olympique de Marsella":
        labels.update({"Marsella", "Marseille"})
    if team == "Olympique de Lyon":
        labels.add("Lyon")
    return sorted(labels, key=len, reverse=True)


def _team_score_parenthesis(report: str, team: str):
    for label in _labels_for_team(team):
        escaped = re.escape(label).replace(r"\ ", r"\s+")
        match = re.search(
            rf"(?i)(?<![\w]){escaped}\s*(\d{{1,2}})\s*\(([^()\n]{{1,300}})\)",
            report,
        )
        if match:
            return int(match.group(1)), match.group(2).strip()
    return None


def _split_scorer_group(raw: str):
    # Evita separar nombres por espacios; solo separadores inequívocos.
    bits = [part.strip() for part in re.split(r"\s*[,;]\s*", str(raw or "")) if part.strip()]
    out = []
    for bit in bits:
        # "Rooney x2", "Rooney ×2" o "Rooney 2x".
        m = re.match(r"^(.*?)(?:\s*[x×]\s*(\d+)|\s+(\d+)\s*[x×])?$", bit, flags=re.I)
        if not m:
            return []
        name = str(m.group(1) or "").strip()
        if not name:
            return []
        goals = int(m.group(2) or m.group(3) or 1)
        if goals < 1 or goals > 20:
            return []
        out.append((name, goals))
    return out


def _extract_explicit_scorers(report: str, payload: dict):
    kind = str(payload.get("kind") or "").casefold()
    if kind not in {"final", "segments"}:
        return []

    home = league.canonical_team(payload.get("home_team"))
    away = league.canonical_team(payload.get("away_team"))
    if not home or not away or home == away:
        return []

    try:
        home_goals = int(payload.get("home_goals"))
        away_goals = int(payload.get("away_goals"))
    except (TypeError, ValueError):
        return []

    scorers = []
    for team, expected in ((home, home_goals), (away, away_goals)):
        found = _team_score_parenthesis(report, team)
        if not found:
            continue
        written_score, raw_group = found
        # Solo asociar la lista cuando el número escrito junto al equipo coincide
        # con el marcador que el intérprete entendió como final.
        if written_score != expected:
            continue
        group = _split_scorer_group(raw_group)
        if not group or sum(goals for _name, goals in group) != expected:
            continue
        scorers.extend(
            {"player": name, "team": team, "goals": int(goals)}
            for name, goals in group
        )
    return scorers


async def _analyze_text_with_scorers(report: str, reporter_club: str | None):
    payload = await _ORIGINAL_ANALYZE_TEXT(report, reporter_club)
    if isinstance(payload, dict):
        explicit = _extract_explicit_scorers(report, payload)
        if explicit:
            payload = dict(payload)
            payload["scorers"] = explicit
            payload["text_scorers_explicit"] = True
    return payload


text_result._analyze_text = _analyze_text_with_scorers


# ---------------------------------------------------------------------------
# Resolver abreviaturas escritas por usuarios contra la plantilla real.
# ---------------------------------------------------------------------------
def _roster_names(runtime, guild_id: int, team: str):
    rows = []
    for row in league.roster(runtime, int(guild_id)):
        if league.canonical_team(row["club"]) == team:
            rows.append(str(row["name"]))
    return rows


def _resolve_written_player(runtime, guild_id: int, raw: str, team: str):
    names = _roster_names(runtime, guild_id, team)
    if not names:
        return None

    key = league.norm(raw)
    keyed = {league.norm(name): name for name in names}
    if key in keyed:
        return keyed[key]

    # Permite abreviaturas inequívocas como "Riquelme" -> "Juan Román Riquelme".
    contains = [name for norm_name, name in keyed.items() if key and (key in norm_name or norm_name in key)]
    if len(contains) == 1:
        return contains[0]

    hit = difflib.get_close_matches(key, list(keyed.keys()), n=2, cutoff=0.72)
    if len(hit) == 1:
        return keyed[hit[0]]
    if len(hit) >= 2:
        # Solo aceptar si el mejor resultado está claramente separado del segundo.
        best = difflib.SequenceMatcher(None, key, hit[0]).ratio()
        second = difflib.SequenceMatcher(None, key, hit[1]).ratio()
        if best - second >= 0.08:
            return keyed[hit[0]]
    return None


def _parsed_scorers_with_text(runtime, guild_id, payload):
    if not isinstance(payload, dict) or payload.get("source_kind") != "text" or not payload.get("text_scorers_explicit"):
        return _ORIGINAL_PARSED_SCORERS(runtime, guild_id, payload)

    output = []
    totals = {}
    for item in payload.get("scorers") or []:
        if not isinstance(item, dict):
            continue
        team = league.canonical_team(item.get("team"))
        if not team:
            continue
        try:
            goals = int(item.get("goals") or 1)
        except (TypeError, ValueError):
            continue
        if goals < 1 or goals > 20:
            continue
        player = _resolve_written_player(runtime, int(guild_id), str(item.get("player") or ""), team)
        if not player:
            continue
        output.append((player, team, goals))
        totals[team] = totals.get(team, 0) + goals

    # No permitir que la declaración de goleadores exceda el marcador oficial.
    home = league.canonical_team(payload.get("home_team"))
    away = league.canonical_team(payload.get("away_team"))
    try:
        limits = {
            home: int(payload.get("home_goals")),
            away: int(payload.get("away_goals")),
        }
    except (TypeError, ValueError):
        return []
    if any(totals.get(team, 0) > limit for team, limit in limits.items() if team):
        return []
    return output


league.parsed_scorers = _parsed_scorers_with_text


# ---------------------------------------------------------------------------
# Mensajes mixtos: texto explícito + captura.
# ---------------------------------------------------------------------------
async def _mixed_text_aware_handle(runtime, bot, message):
    if not message.guild or message.author.bot:
        return await text_result._ORIGINAL_HANDLE(runtime, bot, message)

    report = str(message.content or "").strip()
    has_attachments = bool(message.attachments)

    # Sin texto numérico explícito, una captura sigue exactamente el flujo visual
    # anterior. Esto evita convertir una captura final con un simple "resultado"
    # en una declaración manual.
    if has_attachments and (not report or not text_result._SCORE_RE.search(report)):
        return await text_result._ORIGINAL_HANDLE(runtime, bot, message)
    if not report:
        return await text_result._ORIGINAL_HANDLE(runtime, bot, message)

    intake_id = text_result._configured_intake(runtime, message.guild.id)
    if not intake_id or int(message.channel.id) != int(intake_id):
        return await text_result._ORIGINAL_HANDLE(runtime, bot, message)
    if not text_result._looks_like_text_report(report):
        return await text_result._ORIGINAL_HANDLE(runtime, bot, message)

    match_exists, staged_status, review_status = text_result._existing_source_state(
        runtime, message.guild.id, message.id
    )
    if match_exists:
        await text_result._safe_react(message, "✅")
        return
    if staged_status or review_status:
        return

    if not league.os.getenv("OPENAI_API_KEY"):
        await strict._send_admin_review(
            message,
            "Recibí un resultado escrito, pero el intérprete no tiene OPENAI_API_KEY configurada.",
        )
        return

    await text_result._safe_react(message, "⏳")
    try:
        reporter_club = evidence._club_for_user(runtime, message.guild.id, message.author.id)
        payload = await text_result._analyze_text(report, reporter_club)
        try:
            confidence = float(payload.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        if confidence < text_result.TEXT_MIN_CONF:
            await strict._send_admin_review(
                message,
                f"Leí el relato escrito, pero la interpretación no alcanzó la confianza mínima ({confidence:.0%} < {text_result.TEXT_MIN_CONF:.0%}). No se cargó nada.",
            )
            return

        score, error = text_result._score_from_payload(payload)
        if not score:
            await strict._send_admin_review(message, error)
            return

        await text_result._queue_rival_confirmation(runtime, message, payload, score)
    except Exception as exc:
        print(f"AJAP Liga texto+captura error mensaje={message.id}: {exc}")
        await strict._send_admin_review(
            message,
            "Ocurrió un error técnico al interpretar el resultado escrito. No se modificó la tabla.",
        )
    finally:
        await text_result._remove_processing(message)


text_result._text_aware_handle = _mixed_text_aware_handle


# ---------------------------------------------------------------------------
# Reparación idempotente del partido ya cargado mostrado por el usuario.
# ---------------------------------------------------------------------------
def _repair_everton_villarreal(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    inserted = 0
    try:
        matches = conn.execute(
            """
            SELECT * FROM league_matches
            WHERE ((home_team='Everton' AND away_team='Villarreal')
                OR (home_team='Villarreal' AND away_team='Everton'))
              AND home_goals=1 AND away_goals=1
            """
        ).fetchall()

        for match in matches:
            source_id = int(match["source_message_id"])
            rows = conn.execute(
                """
                SELECT team, SUM(goals) AS goals
                FROM league_goal_events
                WHERE source_message_id=?
                GROUP BY team COLLATE NOCASE
                """,
                (source_id,),
            ).fetchall()
            totals = {
                league.canonical_team(row["team"]): int(row["goals"] or 0)
                for row in rows
                if league.canonical_team(row["team"])
            }

            missing = []
            if totals.get("Everton", 0) == 0:
                missing.append(("Van der Meyde", "Everton"))
            if totals.get("Villarreal", 0) == 0:
                missing.append(("Juan Román Riquelme", "Villarreal"))
            if not missing:
                continue

            conn.execute("BEGIN IMMEDIATE")
            for player, team in missing:
                # No duplicar al jugador aunque exista una fila con team escrito de
                # otra forma.
                exists = conn.execute(
                    """
                    SELECT 1 FROM league_goal_events
                    WHERE source_message_id=? AND player=? COLLATE NOCASE
                    LIMIT 1
                    """,
                    (source_id, player),
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    """
                    INSERT INTO league_goal_events
                        (source_message_id, player, team, goals, confidence)
                    VALUES (?, ?, ?, 1, 1.0)
                    """,
                    (source_id, player, team),
                )
                inserted += 1
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return inserted


async def _repair_existing_match_on_ready():
    if APP is None or BOT is None:
        return
    for guild in list(BOT.guilds):
        try:
            inserted = _repair_everton_villarreal(APP, guild.id)
            if inserted:
                await league.refresh(APP, BOT, guild.id)
                print(
                    f"AJAP Liga reparación Everton/Villarreal guild={guild.id}: "
                    f"{inserted} goleador(es) agregado(s)"
                )
        except Exception as exc:
            print(f"AJAP Liga reparación Everton/Villarreal guild={guild.id} error: {exc}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_text_scorer_repair_patch", False):
        return

    if not getattr(bot, "_ajap_text_scorer_repair_listener", False):
        bot.add_listener(_repair_existing_match_on_ready, "on_ready")
        bot._ajap_text_scorer_repair_listener = True

    runtime._ajap_text_scorer_repair_patch = True
    print("AJAP Liga: goleadores escritos + mensajes mixtos texto/captura activos")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_text_scorers(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_text_scorer_repair_wrapped", False):
    _apply_guild_isolation_then_text_scorers._ajap_text_scorer_repair_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_text_scorers
