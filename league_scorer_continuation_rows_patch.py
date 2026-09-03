"""PES 6 scorer-detail guard: unnamed goals stay unattributed.

League truth and player-scorer truth are intentionally separate:
- the official PES score is authoritative for the match, standings and team stats;
- a goal is credited to an individual player only when that player's name is
  actually visible/readable in the scorer evidence;
- a blank-name row is NEVER inherited by the player above it. Its goal still
  exists in the match score, but it creates no ``league_goal_events`` player row.

This layer keeps a narrow high-detail scorer pass for cases where the primary
vision pass missed a genuinely readable player name. It can enrich named scorer
metadata, but it can never alter the result or fill missing goals by inference.

It also reverses the one historical West Ham 0-6 Manchester City backfill from
an earlier rule that incorrectly changed Hamann 2 -> 4. The rollback is tightly
bounded to that exact match/date/scorer state and is idempotent.
"""

from __future__ import annotations

import base64
import json
import re
import sys
import urllib.error
import urllib.request

import guild_isolation_patch as guild_isolation
import league_automation_patch as league


APP = None
BOT = None
_MIN_REPAIR_CONFIDENCE = 0.82


def _score_limits(payload):
    try:
        return {
            "home": max(0, int(payload.get("home_goals"))),
            "away": max(0, int(payload.get("away_goals"))),
        }
    except (TypeError, ValueError):
        return None


def _canonical_side_for_team(payload, raw_team):
    team = league.canonical_team(raw_team)
    home = league.canonical_team(payload.get("home_team"))
    away = league.canonical_team(payload.get("away_team"))
    if team and home and team == home:
        return "home"
    if team and away and team == away:
        return "away"
    return None


def _current_scorer_totals(payload):
    totals = {"home": 0, "away": 0}
    for item in payload.get("scorers") or []:
        if not isinstance(item, dict):
            continue
        side = _canonical_side_for_team(payload, item.get("team"))
        if not side:
            continue
        try:
            goals = int(item.get("goals") or 1)
        except (TypeError, ValueError):
            continue
        if 1 <= goals <= 30:
            totals[side] += goals
    return totals


def _needs_repair(payload):
    """Try a detail pass when named goals do not cover the official score.

    A shortfall is not itself an error: it can simply mean that PES displayed
    one or more goals with no readable player name. The extra pass only tries to
    recover names that are genuinely visible at higher detail.
    """
    if not isinstance(payload, dict):
        return False
    limits = _score_limits(payload)
    if not limits:
        return False
    kind = str(payload.get("kind") or "").casefold()
    if kind not in {"result", "both"}:
        return False
    current = _current_scorer_totals(payload)
    return any(current[side] < limits[side] for side in ("home", "away"))


def _repair_vision_sync(images, payload):
    """Second scorer-only vision pass. It cannot change the match result."""
    api_key = league.os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    home = str(payload.get("home_team") or "HOME")
    away = str(payload.get("away_team") or "AWAY")
    try:
        hg = int(payload.get("home_goals"))
        ag = int(payload.get("away_goals"))
    except (TypeError, ValueError):
        return None

    prompt = f"""Sos un verificador especializado EXCLUSIVAMENTE en la tabla de GOLEADORES de PES 6.
Analizá todas las imágenes como evidencia del mismo partido. El resultado ya está fijado y NO lo podés cambiar:
HOME = {home}, goles HOME = {hg}
AWAY = {away}, goles AWAY = {ag}

Devolvé SOLO JSON válido, sin markdown:
{{"scorers":[{{"player":"","side":"home|away","goals":1}}],"confidence":0.0,"unnamed_home":0,"unnamed_away":0,"notes":""}}

REGLA CRÍTICA — GOLES SIN NOMBRE:
- Si una fila/minuto de gol aparece SIN nombre de jugador, ese gol cuenta para el MARCADOR DEL EQUIPO, pero NO se asocia a ningún jugador.
- NUNCA heredes el nombre del jugador de la fila anterior, aunque la fila vacía esté inmediatamente debajo o alineada en la misma columna.
- NUNCA supongas que una fila vacía es una continuación del jugador superior.
- NUNCA inventes un nombre para hacer coincidir la suma de goleadores con el marcador.
- Los goles sin nombre NO deben aparecer dentro de `scorers`.
- Contalos solamente en `unnamed_home` o `unnamed_away` como dato de auditoría.

Ejemplo:
`Hamann | 6' 41'` y debajo `        | 43' 79'` significa:
- Hamann = 2 goles identificados.
- 2 goles adicionales del equipo = sin autor identificado.
- El marcador del equipo puede ser 4, pero Hamann NO pasa a tener 4.

Reglas adicionales:
- Incluí en `scorers` solamente nombres que sean realmente visibles y legibles en la captura.
- `side=home` corresponde a HOME y `side=away` a AWAY.
- Consolidá un mismo jugador en una sola entrada si su NOMBRE sí aparece en varias filas.
- La suma de goleadores identificados de un lado NO puede superar {hg} para home ni {ag} para away.
- No uses conocimiento externo de fútbol ni de plantillas para completar nombres.
- Si hay duda sobre un nombre, dejá ese gol sin atribuir.
- confidence mide la certeza de esta lectura específica de los NOMBRES visibles.
"""

    content = [{"type": "input_text", "text": prompt}]
    for data, mime in images:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}",
                "detail": "high",
            }
        )

    body = json.dumps(
        {
            "model": league.MODEL,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": 900,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        league.API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=75) as res:
            response = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"OpenAI scorer detail HTTP {exc.code}: {detail}") from exc

    text = league.response_text(response)
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    parsed = json.loads(text[start : end + 1])
    return parsed if isinstance(parsed, dict) else None


def _merge_repair(payload, repair):
    """Merge only positively named scorer evidence; preserve existing names."""
    if not isinstance(repair, dict):
        return payload
    try:
        confidence = float(repair.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < _MIN_REPAIR_CONFIDENCE:
        return payload

    limits = _score_limits(payload)
    if not limits:
        return payload

    merged = {}

    # Start from the primary pass so the detail pass can never erase an already
    # identified scorer merely because it omitted that player on retry.
    for item in payload.get("scorers") or []:
        if not isinstance(item, dict):
            continue
        side = _canonical_side_for_team(payload, item.get("team"))
        player = str(item.get("player") or "").strip()
        if side not in {"home", "away"} or not player:
            continue
        try:
            goals = int(item.get("goals") or 1)
        except (TypeError, ValueError):
            continue
        if not (1 <= goals <= 30):
            continue
        key = (league.norm(player), side)
        if key[0]:
            merged[key] = {"player": player[:100], "side": side, "goals": goals}

    current_totals = _current_scorer_totals(payload)

    # Add/improve only rows with an explicit player name returned by the focused
    # pass. Blank/unknown rows are intentionally ignored here.
    for item in repair.get("scorers") or []:
        if not isinstance(item, dict):
            continue
        side = str(item.get("side") or "").casefold()
        player = str(item.get("player") or "").strip()
        if side not in {"home", "away"} or not player:
            continue
        try:
            goals = int(item.get("goals") or 1)
        except (TypeError, ValueError):
            continue
        if not (1 <= goals <= 30):
            continue
        key = (league.norm(player), side)
        if not key[0]:
            continue
        prior = merged.get(key)
        if prior is None or goals > int(prior["goals"]):
            merged[key] = {"player": player[:100], "side": side, "goals": goals}

    repaired_totals = {"home": 0, "away": 0}
    for item in merged.values():
        repaired_totals[item["side"]] += int(item["goals"])

    if any(repaired_totals[side] > limits[side] for side in ("home", "away")):
        return payload

    current_known = sum(min(current_totals[s], limits[s]) for s in ("home", "away"))
    repaired_known = sum(repaired_totals.values())
    if repaired_known <= current_known:
        return payload

    repaired_items = []
    for item in merged.values():
        team = payload.get("home_team") if item["side"] == "home" else payload.get("away_team")
        repaired_items.append(
            {"player": item["player"], "team": team, "goals": int(item["goals"])}
        )

    out = dict(payload)
    out["scorers"] = repaired_items
    if str(out.get("kind") or "").casefold() == "result":
        out["kind"] = "both"
    out["scorer_detail_repair"] = True
    out["scorer_repair_confidence"] = confidence
    try:
        out["unnamed_home"] = max(0, int(repair.get("unnamed_home") or 0))
        out["unnamed_away"] = max(0, int(repair.get("unnamed_away") or 0))
    except (TypeError, ValueError):
        pass
    notes = str(out.get("notes") or "").strip()
    audit = (
        "AJAP scorer detail: "
        f"home identificados {current_totals['home']}->{repaired_totals['home']}/{limits['home']}, "
        f"away identificados {current_totals['away']}->{repaired_totals['away']}/{limits['away']}"
    )
    out["notes"] = (notes + (" | " if notes else "") + audit)[:1000]
    return out


def _install_future_repair(runtime):
    current = league.analyze
    if getattr(current, "_ajap_pes_scorer_continuation", False):
        return

    async def analyze_with_named_scorer_guard(images):
        payload = await current(images)
        if not _needs_repair(payload):
            return payload
        try:
            repair = await league.asyncio.to_thread(_repair_vision_sync, images, payload)
            return _merge_repair(payload, repair)
        except Exception as exc:
            # Scorer detail is enrichment only. The official result remains valid
            # even when one or more goals have no identified author.
            print(f"WARNING AJAP scorer detail pass: {type(exc).__name__}: {exc}")
            return payload

    analyze_with_named_scorer_guard.__name__ = getattr(current, "__name__", "analyze")
    # Keep the historical marker name so repeated installs remain idempotent.
    analyze_with_named_scorer_guard._ajap_pes_scorer_continuation = True
    analyze_with_named_scorer_guard._ajap_pes_scorer_continuation_base = current
    league.analyze = analyze_with_named_scorer_guard


def _surname_key(player):
    value = league.norm(player)
    for wanted in ("samaras", "hamann", "vassel"):
        if wanted in value.split() or value.endswith(wanted) or wanted in value:
            return wanted
    return value


def _undo_wrong_city_backfill(runtime, guild_id: int):
    """Undo only the exact Hamann 2->4 attribution introduced by prior code."""
    conn = league.db(runtime, int(guild_id))
    changed = 0
    try:
        matches = conn.execute(
            """
            SELECT * FROM league_matches
            WHERE created_at >= '2026-09-02 00:00:00'
              AND created_at <  '2026-09-04 00:00:00'
              AND (
                    (home_team='West Ham United' AND away_team='Manchester City'
                     AND home_goals=0 AND away_goals=6)
                 OR (home_team='Manchester City' AND away_team='West Ham United'
                     AND home_goals=6 AND away_goals=0)
              )
            ORDER BY id DESC
            """
        ).fetchall()

        for match in matches:
            source_id = int(match["source_message_id"])
            rows = conn.execute(
                """
                SELECT id, player, team, goals
                FROM league_goal_events
                WHERE source_message_id=?
                ORDER BY id ASC
                """,
                (source_id,),
            ).fetchall()
            city_rows = [
                row for row in rows
                if league.canonical_team(row["team"]) == "Manchester City"
            ]
            if not city_rows:
                continue

            totals = {}
            ids = {}
            total_city = 0
            for row in city_rows:
                key = _surname_key(row["player"])
                goals = int(row["goals"] or 0)
                totals[key] = totals.get(key, 0) + goals
                ids.setdefault(key, []).append((int(row["id"]), goals))
                total_city += goals

            # Exact erroneous after-state created by the previous deployment.
            # Legitimate data with any other pattern is left untouched.
            if total_city != 6 or totals != {"samaras": 1, "hamann": 4, "vassel": 1}:
                continue

            hamann_rows = ids.get("hamann") or []
            if not hamann_rows:
                continue
            first_id, first_goals = hamann_rows[0]
            if first_goals < 3:
                continue

            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE league_goal_events SET goals=? WHERE id=?",
                (int(first_goals) - 2, int(first_id)),
            )
            conn.commit()
            changed += 1
            print(
                "AJAP scorer correction: West Ham 0-6 Manchester City "
                f"source={source_id} • Hamann 4->2 • 2 goles quedan sin autor"
            )
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return changed


async def _refresh_optional_ges_cards(runtime, bot):
    details = sys.modules.get("league_ges_scorer_details_patch")
    if details is None:
        return
    refresher = getattr(details, "_refresh_active_ges_cards", None)
    if not callable(refresher):
        return
    try:
        if hasattr(details, "APP"):
            details.APP = runtime
        if hasattr(details, "BOT"):
            details.BOT = bot
        await refresher()
    except Exception as exc:
        print(f"WARNING AJAP scorer correction GES refresh: {type(exc).__name__}: {exc}")


async def _undo_wrong_city_on_ready():
    if APP is None or BOT is None:
        return
    any_changed = False
    for guild in list(BOT.guilds):
        try:
            changed = _undo_wrong_city_backfill(APP, guild.id)
            if not changed:
                continue
            any_changed = True
            await league.refresh(APP, BOT, guild.id)
        except Exception as exc:
            print(
                f"WARNING AJAP scorer correction guild={getattr(guild, 'id', '?')}: "
                f"{type(exc).__name__}: {exc}"
            )
    if any_changed:
        await _refresh_optional_ges_cards(APP, BOT)


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_scorer_continuation_rows_patch", False):
        return

    _install_future_repair(runtime)
    if not getattr(bot, "_ajap_scorer_continuation_backfill_listener", False):
        bot.add_listener(_undo_wrong_city_on_ready, "on_ready")
        bot._ajap_scorer_continuation_backfill_listener = True

    runtime._ajap_scorer_continuation_rows_patch = True
    print(
        "AJAP goleadores PES6: goles sin nombre cuentan al marcador pero no a jugadores"
    )


_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_scorer_continuation_rows_wrapper",
    False,
):
    _apply._ajap_scorer_continuation_rows_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
