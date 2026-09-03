"""One-time authoritative repair for the latest misread Feyenoord result.

The affected result was incorrectly persisted as:
    Feyenoord 2-2 Tottenham Hotspur
The user-confirmed official result is:
    Feyenoord 1-1 Real Zaragoza

The repair targets only the newest exact Feyenoord/Tottenham 2-2 source and keeps
all persisted Liga/GES representations aligned. Wrong scorer rows are removed;
we do not invent scorer names for the corrected 1-1.
"""
from __future__ import annotations

import json

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_ges_result_queue_patch as ges

APP = None
BOT = None
_MARKER = "fix_feyenoord_tottenham_2_2_to_zaragoza_1_1_v1"


def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone())


def _columns(conn, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _wrong_pair(home, away, hg, ag) -> bool:
    try:
        if int(hg) != 2 or int(ag) != 2:
            return False
    except Exception:
        return False
    pair = {str(home or "").strip().casefold(), str(away or "").strip().casefold()}
    return pair == {"feyenoord", "tottenham hotspur"}


def _find_source(conn):
    candidates = set()
    for table in ("league_matches", "league_ges_result_queue", "league_result_evidence"):
        cols = _columns(conn, table)
        needed = {"source_message_id", "home_team", "away_team", "home_goals", "away_goals"}
        if not needed.issubset(cols):
            continue
        rows = conn.execute(
            f"SELECT source_message_id,home_team,away_team,home_goals,away_goals FROM {table} "
            "WHERE home_goals=2 AND away_goals=2 ORDER BY source_message_id DESC LIMIT 25"
        ).fetchall()
        for row in rows:
            if _wrong_pair(row["home_team"], row["away_team"], row["home_goals"], row["away_goals"]):
                candidates.add(int(row["source_message_id"]))
    return max(candidates) if candidates else None


def _fixed_payload(raw):
    try:
        payload = json.loads(raw or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.update({
        "kind": "result",
        "match_state": "final",
        "home_team": "Feyenoord",
        "away_team": "Real Zaragoza",
        "home_goals": 1,
        "away_goals": 1,
        "scorers": [],
        "confidence": 1.0,
        "result_confidence": 1.0,
        "scorers_confidence": 0.0,
        "notes": "Corrección administrativa: Feyenoord 1-1 Real Zaragoza; lectura previa Feyenoord 2-2 Tottenham descartada.",
    })
    for key in ("pes_link_applied", "pes_link_ambiguous", "multisignal_sources"):
        payload.pop(key, None)
    return json.dumps(payload, ensure_ascii=False)


def _repair_db(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS league_history_migrations ("
            "name TEXT PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        if conn.execute("SELECT 1 FROM league_history_migrations WHERE name=?", (_MARKER,)).fetchone():
            return None

        source_id = _find_source(conn)
        if not source_id:
            return None

        conn.execute("BEGIN IMMEDIATE")

        if _table_exists(conn, "league_matches"):
            conn.execute(
                "UPDATE league_matches SET home_team='Feyenoord',away_team='Real Zaragoza',"
                "home_goals=1,away_goals=1,confidence=1.0 WHERE source_message_id=?",
                (source_id,),
            )

        if _table_exists(conn, "league_ges_result_queue"):
            cols = _columns(conn, "league_ges_result_queue")
            conn.execute(
                "UPDATE league_ges_result_queue SET home_team='Feyenoord',away_team='Real Zaragoza',"
                "home_goals=1,away_goals=1" + (",updated_at=CURRENT_TIMESTAMP" if "updated_at" in cols else "") +
                " WHERE source_message_id=?",
                (source_id,),
            )

        if _table_exists(conn, "league_result_evidence"):
            cols = _columns(conn, "league_result_evidence")
            row = conn.execute(
                "SELECT payload_json FROM league_result_evidence WHERE source_message_id=?", (source_id,)
            ).fetchone()
            set_bits = ["home_team='Feyenoord'", "away_team='Real Zaragoza'", "home_goals=1", "away_goals=1"]
            params = []
            if "confidence" in cols:
                set_bits.append("confidence=1.0")
            if "match_state" in cols:
                set_bits.append("match_state='final'")
            if "payload_json" in cols:
                set_bits.append("payload_json=?")
                params.append(_fixed_payload(row["payload_json"] if row else None))
            if "updated_at" in cols:
                set_bits.append("updated_at=CURRENT_TIMESTAMP")
            params.append(source_id)
            conn.execute(
                "UPDATE league_result_evidence SET " + ",".join(set_bits) + " WHERE source_message_id=?",
                tuple(params),
            )

        if _table_exists(conn, "league_manual_reviews"):
            cols = _columns(conn, "league_manual_reviews")
            set_bits = ["home_team='Feyenoord'", "away_team='Real Zaragoza'", "home_goals=1", "away_goals=1"]
            if "reason" in cols:
                set_bits.append("reason='Resultado corregido administrativamente: Feyenoord 1-1 Real Zaragoza.'")
            conn.execute(
                "UPDATE league_manual_reviews SET " + ",".join(set_bits) + " WHERE source_message_id=?",
                (source_id,),
            )

        # The previously detected 2-2 scorer attribution cannot be trusted after
        # both opponent and score changed. Leave one missing goal per side visible.
        if _table_exists(conn, "league_goal_events"):
            conn.execute("DELETE FROM league_goal_events WHERE source_message_id=?", (source_id,))

        conn.execute("INSERT INTO league_history_migrations(name) VALUES (?)", (_MARKER,))
        conn.commit()
        return source_id
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


async def _refresh_ges(runtime, bot, guild, source_id: int):
    try:
        row = ges._find(runtime, guild.id, source=source_id)
        if not row or not row["ges_message_id"] or not row["ges_channel_id"]:
            return
        channel = guild.get_channel(int(row["ges_channel_id"]))
        if channel is None:
            channel = await bot.fetch_channel(int(row["ges_channel_id"]))
        message = await channel.fetch_message(int(row["ges_message_id"]))
        row = ges._find(runtime, guild.id, source=source_id)
        embed = ges._embed(guild, row, row["status_by"])
        image = await ges._card(guild, "Feyenoord", "Real Zaragoza", 1, 1)
        embed.set_image(url="attachment://ges_resultado.png")
        await message.edit(
            embed=embed,
            attachments=[discord.File(image, filename="ges_resultado.png")],
            view=ges.GesView(str(row["status"] or "PENDIENTE")),
        )
    except Exception as exc:
        print(f"WARNING AJAP Feyenoord/Zaragoza GES refresh: {type(exc).__name__}: {exc}")


async def _run_fix():
    if APP is None or BOT is None:
        return
    for guild in list(BOT.guilds):
        try:
            source_id = _repair_db(APP, guild.id)
            if not source_id:
                continue
            print(
                "AJAP authoritative result fix applied: "
                f"source={source_id} • Feyenoord 1-1 Real Zaragoza"
            )
            await _refresh_ges(APP, BOT, guild, source_id)
            try:
                await league.refresh(APP, BOT, guild.id)
            except Exception as exc:
                print(f"WARNING AJAP Feyenoord/Zaragoza league refresh: {exc}")
        except Exception as exc:
            print(
                f"WARNING AJAP Feyenoord/Zaragoza repair guild={getattr(guild,'id','?')}: "
                f"{type(exc).__name__}: {exc}"
            )


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_feyenoord_zaragoza_result_fix", False):
        return
    if not getattr(bot, "_ajap_feyenoord_zaragoza_result_fix_listener", False):
        bot.add_listener(_run_fix, "on_ready")
        bot._ajap_feyenoord_zaragoza_result_fix_listener = True
    runtime._ajap_feyenoord_zaragoza_result_fix = True
    print("AJAP correction armed: Feyenoord 2-2 Tottenham -> Feyenoord 1-1 Real Zaragoza")


_PREVIOUS = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _PREVIOUS(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_feyenoord_zaragoza_result_fix_wrapper", False):
    _apply._ajap_feyenoord_zaragoza_result_fix_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
