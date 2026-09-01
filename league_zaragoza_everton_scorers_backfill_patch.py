"""One-time scorer backfill for the Staff-resolved Zaragoza vs Everton result.

The original PES screenshot clearly shows:
- Everton (Merseyside Blue): Van der Meyde 24', Beattie 55'
- Real Zaragoza: Aimar 30', D. Milito 56' and 83'

That match had already been loaded manually before the manual-scorer parity fix,
so the score exists in league_matches but the corresponding league_goal_events
were never persisted. This patch repairs only that already-resolved historical
manual review, is idempotent, and refreshes Liga after applying it.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league


APP = None
BOT = None

_DESIRED = (
    ("Van der Meyde", "Everton", 1),
    ("Beattie", "Everton", 1),
    ("Aimar", "Real Zaragoza", 1),
    ("D. Milito", "Real Zaragoza", 2),
)


def _canonical(value):
    return league.canonical_team(value) or str(value or "").strip()


def _target_match(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            """
            SELECT m.*
            FROM league_matches m
            JOIN league_manual_reviews r
              ON r.source_message_id = m.source_message_id
            WHERE UPPER(COALESCE(r.status, '')) = 'RESUELTO'
              AND datetime(m.created_at) < datetime('2026-09-02 00:00:00')
            ORDER BY m.created_at DESC
            """
        ).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()

    for row in rows:
        home = _canonical(row["home_team"])
        away = _canonical(row["away_team"])
        hg = int(row["home_goals"])
        ag = int(row["away_goals"])

        if home == "Everton" and away == "Real Zaragoza" and hg == 2 and ag == 3:
            return row
        if home == "Real Zaragoza" and away == "Everton" and hg == 3 and ag == 2:
            return row
    return None


def _current(runtime, guild_id: int, source_message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            """
            SELECT player, team, SUM(goals) AS goals
            FROM league_goal_events
            WHERE source_message_id=?
            GROUP BY player COLLATE NOCASE, COALESCE(team, '') COLLATE NOCASE
            """,
            (int(source_message_id),),
        ).fetchall()
    finally:
        conn.close()
    return {
        (league.norm(row["player"]), _canonical(row["team"])): int(row["goals"] or 0)
        for row in rows
    }


def _desired_map():
    return {
        (league.norm(player), club): int(goals)
        for player, club, goals in _DESIRED
    }


def _backfill(runtime, guild_id: int):
    match = _target_match(runtime, int(guild_id))
    if not match:
        return False

    source_id = int(match["source_message_id"])
    if _current(runtime, guild_id, source_id) == _desired_map():
        return False

    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM league_goal_events WHERE source_message_id=?",
            (source_id,),
        )
        for player, club, goals in _DESIRED:
            conn.execute(
                """
                INSERT INTO league_goal_events
                    (source_message_id, player, team, goals, confidence)
                VALUES (?, ?, ?, ?, 1.0)
                """,
                (source_id, player, club, int(goals)),
            )
        conn.commit()
        print(
            "AJAP Liga backfill: Everton 2-3 Real Zaragoza -> "
            "Van der Meyde, Beattie, Aimar, D. Milito x2"
        )
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _refresh_if_needed(runtime, bot, guild_id: int):
    try:
        changed = _backfill(runtime, int(guild_id))
    except Exception as exc:
        print(
            f"AJAP Liga backfill goleadores guild={guild_id}: "
            f"{type(exc).__name__}: {exc}"
        )
        return
    if changed:
        try:
            await league.refresh(runtime, bot, int(guild_id))
        except Exception as exc:
            print(f"AJAP Liga backfill: refresh falló guild={guild_id}: {exc}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_zaragoza_everton_scorers_backfill", False):
        return

    @bot.listen("on_ready")
    async def _ajap_backfill_zaragoza_everton_scorers():
        # Search every connected guild, but the target itself is constrained to
        # the historical, resolved manual result and its exact 3-2 score.
        for guild in list(bot.guilds):
            await _refresh_if_needed(runtime, bot, int(guild.id))

    runtime._ajap_zaragoza_everton_scorers_backfill = True
    print("AJAP Liga: backfill histórico Zaragoza/Everton listo")


_ORIGINAL = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_zaragoza_everton_scorers_backfill_wrapper",
    False,
):
    _apply._ajap_zaragoza_everton_scorers_backfill_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
