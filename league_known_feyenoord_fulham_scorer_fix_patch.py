"""One-time bounded scorer correction for the confirmed Feyenoord 4-1 Fulham result.

User-confirmed scorers:
- Feyenoord: Kolka x2, Van Hooijdonk x1, Boussaboun x1
- Fulham: Boa Morte x1

Safety boundaries:
- only matches created on 2026-09-04 or 2026-09-05 (covers local/UTC rollover);
- only Feyenoord 4-1 Fulham, in either home/away orientation;
- only a result that also exists in the GES result queue;
- only when that source has ZERO league_goal_events already recorded;
- correction runs only if exactly one candidate exists in the guild.

The official score is never modified.
"""

from __future__ import annotations

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_ges_scorer_details_patch as ges_details

APP = None
BOT = None


def _candidate(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        queue_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='league_ges_result_queue' LIMIT 1"
        ).fetchone()
        if not queue_exists:
            return None

        rows = conn.execute(
            """
            SELECT m.*
            FROM league_matches m
            JOIN league_ges_result_queue q
              ON q.source_message_id = m.source_message_id
            WHERE m.created_at >= '2026-09-04 00:00:00'
              AND m.created_at <  '2026-09-06 00:00:00'
              AND (
                    (m.home_team='Feyenoord' AND m.away_team='Fulham' AND m.home_goals=4 AND m.away_goals=1)
                 OR (m.home_team='Fulham' AND m.away_team='Feyenoord' AND m.home_goals=1 AND m.away_goals=4)
              )
              AND NOT EXISTS (
                    SELECT 1
                    FROM league_goal_events g
                    WHERE g.source_message_id = m.source_message_id
              )
            ORDER BY m.id DESC
            """
        ).fetchall()
        return rows[0] if len(rows) == 1 else None
    finally:
        conn.close()


def _apply_known_fix(runtime, guild_id: int):
    match = _candidate(runtime, guild_id)
    if not match:
        return None

    source_id = int(match['source_message_id'])
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute(
            'SELECT 1 FROM league_goal_events WHERE source_message_id=? LIMIT 1',
            (source_id,),
        ).fetchone():
            conn.rollback()
            return None

        scorers = (
            ('Kolka', 'Feyenoord', 2),
            ('Van Hooijdonk', 'Feyenoord', 1),
            ('Boussaboun', 'Feyenoord', 1),
            ('Boa Morte', 'Fulham', 1),
        )
        for player, team, goals in scorers:
            conn.execute(
                """
                INSERT INTO league_goal_events
                    (source_message_id, player, team, goals, confidence)
                VALUES (?, ?, ?, ?, 1.0)
                """,
                (source_id, player, team, goals),
            )

        conn.commit()
        print(
            'AJAP known scorer correction: Feyenoord 4-1 Fulham '
            f'source={source_id} • Kolka x2 • Van Hooijdonk • Boussaboun • Boa Morte'
        )
        return source_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _known_fix_on_ready():
    if APP is None or BOT is None:
        return

    changed = False
    for guild in list(BOT.guilds):
        try:
            source_id = _apply_known_fix(APP, guild.id)
            if not source_id:
                continue
            changed = True
            await league.refresh(APP, BOT, guild.id)
        except Exception as exc:
            print(
                f"WARNING AJAP Feyenoord-Fulham scorer correction guild={getattr(guild, 'id', '?')}: "
                f"{type(exc).__name__}: {exc}"
            )

    if changed:
        try:
            ges_details.APP = APP
            ges_details.BOT = BOT
            await ges_details._refresh_active_ges_cards()
        except Exception as exc:
            print(
                'WARNING AJAP Feyenoord-Fulham GES refresh: '
                f'{type(exc).__name__}: {exc}'
            )


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, '_ajap_known_feyenoord_fulham_scorer_fix', False):
        return

    if not getattr(bot, '_ajap_known_feyenoord_fulham_scorer_listener', False):
        bot.add_listener(_known_fix_on_ready, 'on_ready')
        bot._ajap_known_feyenoord_fulham_scorer_listener = True

    runtime._ajap_known_feyenoord_fulham_scorer_fix = True
    print('AJAP known correction armed: Feyenoord 4-1 Fulham scorers')


_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    '_ajap_known_feyenoord_fulham_scorer_fix_wrapper',
    False,
):
    _apply._ajap_known_feyenoord_fulham_scorer_fix_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
