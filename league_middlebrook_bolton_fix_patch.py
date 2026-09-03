"""AJAP Liga: map PES 6 Middlebrook to Bolton Wanderers and repair one result.

The PES 6 screen can show Bolton Wanderers under the unlicensed in-game name
"Middlebrook". Without an explicit mapping, fuzzy team matching can confuse it
with Middlesbrough. This patch makes the mapping explicit for future captures and
repairs the already-confirmed Real Zaragoza 2-0 result submitted on 2026-09-02.

The historical repair is intentionally narrow and idempotent: it only touches the
Middlesbrough 0-2 Real Zaragoza row created around the Discord submission visible
at 21:18 Argentina time (00:18 UTC on 2026-09-03).
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request

import guild_isolation_patch as guild_isolation
import league_automation_patch as league


APP = None
BOT = None

# PES 6 unlicensed club name. Keep this explicit so fuzzy matching never sends
# Middlebrook to Middlesbrough again.
league.ALIASES["middlebrook"] = "Bolton Wanderers"


def _vision_sync(images):
    """Evidence vision reader with the PES 6 Middlebrook alias made explicit."""
    api_key = league.os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY")

    prompt = """Sos el lector automático de capturas de una liga de PES 6.
Analizá TODAS las imágenes del mismo mensaje como evidencia del mismo partido/envío.
Devolvé SOLAMENTE un objeto JSON válido, sin markdown, con este formato:
{"kind":"result|scorers|both|unknown","match_state":"final|partial|unknown","home_team":"","away_team":"","home_goals":null,"away_goals":null,"scorers":[{"player":"","team":"","goals":1}],"confidence":0.0,"notes":""}

Reglas estrictas:
- result: se ve claramente un marcador y los dos equipos.
- scorers: se ven claramente nombres de jugadores y cuántos goles hicieron.
- both: hay evidencia clara de ambos.
- unknown: no hay suficiente información.
- match_state=final SOLO si la imagen contiene evidencia visual clara de que el partido terminó: pantalla post-partido/resultado final, texto de fin, menú posterior al partido u otra señal inequívoca.
- match_state=partial si se ve entretiempo, primer tiempo, pausa dentro del partido, reloj de primera mitad u otra evidencia clara de que el encuentro todavía no terminó.
- match_state=unknown si se puede leer un marcador pero NO hay evidencia suficiente para saber si es final o parcial.
- NUNCA deduzcas que un marcador es final solo porque parece razonable o porque se ve un score.
- No inventes. Si una parte no se puede leer, omitila o usá unknown.
- confidence es de 0 a 1 y representa la confianza de la extracción completa.
- En scorers, si un jugador aparece varias veces en las capturas de este mensaje, consolidalo en una sola entrada con su total de goles.
- IMPORTANTE PES 6: si en la pantalla aparece "Middlebrook", ese equipo es BOLTON WANDERERS. Devolvé exactamente "Bolton Wanderers". No lo confundas con Middlesbrough.
- Los nombres de equipos válidos son exactamente: """ + ", ".join(league.TEAMS)

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
            "max_output_tokens": 1400,
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
            payload = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc

    text = league.response_text(payload)
    if not text:
        raise RuntimeError("La API no devolvió texto")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("La respuesta de visión no contiene JSON")
    payload = json.loads(text[start : end + 1])

    # Defensive fallback: if the model preserves the PES name literally, turn it
    # into the canonical AJAP club before the normal parser sees it.
    for key in ("home_team", "away_team"):
        if league.norm(payload.get(key)) == "middlebrook":
            payload[key] = "Bolton Wanderers"
    for scorer in payload.get("scorers") or []:
        if isinstance(scorer, dict) and league.norm(scorer.get("team")) == "middlebrook":
            scorer["team"] = "Bolton Wanderers"
    return payload


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
    )


def _target(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            """
            SELECT * FROM league_matches
            WHERE datetime(created_at) >= datetime('2026-09-03 00:05:00')
              AND datetime(created_at) <= datetime('2026-09-03 00:35:00')
              AND home_goals = 0
              AND away_goals = 2
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    matches = []
    for row in rows:
        home = league.canonical_team(row["home_team"]) or str(row["home_team"] or "").strip()
        away = league.canonical_team(row["away_team"]) or str(row["away_team"] or "").strip()
        if home == "Middlesbrough" and away == "Real Zaragoza":
            matches.append(row)

    # Never guess if somehow more than one exact candidate exists in this narrow window.
    return matches[0] if len(matches) == 1 else None


def _repair(runtime, guild_id: int):
    match = _target(runtime, int(guild_id))
    if not match:
        return False

    source_id = int(match["source_message_id"])
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE league_matches SET home_team='Bolton Wanderers' WHERE source_message_id=? AND home_team=?",
            (source_id, match["home_team"]),
        )

        # Zero goals were scored by Bolton in this result, but keep any related
        # scorer rows consistent in case extra evidence was attached later.
        if _table_exists(conn, "league_goal_events"):
            conn.execute(
                "UPDATE league_goal_events SET team='Bolton Wanderers' WHERE source_message_id=? AND team='Middlesbrough' COLLATE NOCASE",
                (source_id,),
            )

        # The evidence row is also used by review/audit UI, so correct it too.
        if _table_exists(conn, "league_result_evidence"):
            evidence = conn.execute(
                "SELECT payload_json FROM league_result_evidence WHERE source_message_id=? LIMIT 1",
                (source_id,),
            ).fetchone()
            payload_json = evidence["payload_json"] if evidence else None
            if payload_json:
                try:
                    payload = json.loads(payload_json)
                    if league.canonical_team(payload.get("home_team")) == "Middlesbrough":
                        payload["home_team"] = "Bolton Wanderers"
                    payload_json = json.dumps(payload, ensure_ascii=False)
                except Exception:
                    pass
            conn.execute(
                """
                UPDATE league_result_evidence
                SET home_team='Bolton Wanderers', payload_json=COALESCE(?, payload_json),
                    updated_at=CURRENT_TIMESTAMP
                WHERE source_message_id=? AND home_team='Middlesbrough' COLLATE NOCASE
                """,
                (payload_json, source_id),
            )

        conn.commit()
        print(
            "AJAP Liga repair: Middlebrook/Middlesbrough 0-2 Real Zaragoza -> "
            f"Bolton Wanderers 0-2 Real Zaragoza | source={source_id}"
        )
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _repair_and_refresh(runtime, bot, guild_id: int):
    try:
        changed = _repair(runtime, int(guild_id))
    except Exception as exc:
        print(f"AJAP Liga Middlebrook repair guild={guild_id}: {type(exc).__name__}: {exc}")
        return
    if changed:
        try:
            await league.refresh(runtime, bot, int(guild_id))
        except Exception as exc:
            print(f"AJAP Liga Middlebrook repair refresh guild={guild_id}: {exc}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_middlebrook_bolton_fix", False):
        return

    # league_result_evidence_patch installs its own conservative reader first;
    # this layer keeps the same contract and adds the explicit PES alias.
    league.ALIASES["middlebrook"] = "Bolton Wanderers"
    league.vision_sync = _vision_sync

    @bot.listen("on_ready")
    async def _ajap_repair_middlebrook_bolton_result():
        for guild in list(bot.guilds):
            await _repair_and_refresh(runtime, bot, int(guild.id))

    runtime._ajap_middlebrook_bolton_fix = True
    print("AJAP Liga: Middlebrook = Bolton Wanderers + reparación histórica lista")


_ORIGINAL = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_middlebrook_bolton_fix_wrapper", False):
    _apply._ajap_middlebrook_bolton_fix_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
