"""One-time bounded repair for the confirmed Ajax 2-2 Feyenoord capture.

The reader previously mixed one LARGE final-score digit with a small `1er/2do`
subtotal and persisted Ajax 2-0 Feyenoord.  User evidence confirms:
- final score: Ajax 2-2 Feyenoord;
- Ajax scorers already persisted by the reader: Rosales, Mitea;
- visible Feyenoord scorer: Van Hooijdonk x1;
- the second Feyenoord scorer is not safely readable from the supplied evidence,
  so one Feyenoord goal deliberately remains without an attributed player.

Safety boundaries are intentionally narrow: recent date window, exact erroneous
2-0 orientation, matching GES queue, exactly two Ajax goals, Rosales + Mitea,
zero existing Feyenoord goal events, and exactly one candidate per guild.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_ges_result_queue_patch as ges
import league_ges_scorer_details_patch as ges_details

APP = None
BOT = None


def _candidate(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            """
            SELECT m.*
            FROM league_matches m
            JOIN league_ges_result_queue q
              ON q.source_message_id = m.source_message_id
            WHERE m.created_at >= '2026-09-04 00:00:00'
              AND m.created_at <  '2026-09-06 00:00:00'
              AND m.home_team='Ajax'
              AND m.away_team='Feyenoord'
              AND m.home_goals=2
              AND m.away_goals=0
              AND q.home_team='Ajax'
              AND q.away_team='Feyenoord'
              AND q.home_goals=2
              AND q.away_goals=0
              AND (
                    SELECT COALESCE(SUM(g.goals), 0)
                    FROM league_goal_events g
                    WHERE g.source_message_id=m.source_message_id
                      AND g.team='Ajax'
                  ) = 2
              AND EXISTS (
                    SELECT 1 FROM league_goal_events g
                    WHERE g.source_message_id=m.source_message_id
                      AND g.team='Ajax'
                      AND LOWER(g.player) LIKE '%rosales%'
                  )
              AND EXISTS (
                    SELECT 1 FROM league_goal_events g
                    WHERE g.source_message_id=m.source_message_id
                      AND g.team='Ajax'
                      AND LOWER(g.player) LIKE '%mitea%'
                  )
              AND NOT EXISTS (
                    SELECT 1 FROM league_goal_events g
                    WHERE g.source_message_id=m.source_message_id
                      AND g.team='Feyenoord'
                  )
            ORDER BY m.id DESC
            """
        ).fetchall()
        return rows[0] if len(rows) == 1 else None
    finally:
        conn.close()


def _apply_fix(runtime, guild_id: int):
    match = _candidate(runtime, guild_id)
    if not match:
        return None

    match_id = int(match['id'])
    source_id = int(match['source_message_id'])
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute('BEGIN IMMEDIATE')
        current = conn.execute(
            """
            SELECT home_team,away_team,home_goals,away_goals
            FROM league_matches
            WHERE id=? AND source_message_id=?
            LIMIT 1
            """,
            (match_id, source_id),
        ).fetchone()
        if not current or not (
            current['home_team'] == 'Ajax'
            and current['away_team'] == 'Feyenoord'
            and int(current['home_goals']) == 2
            and int(current['away_goals']) == 0
        ):
            conn.rollback()
            return None

        conn.execute(
            "UPDATE league_matches SET away_goals=2 WHERE id=? AND away_goals=0",
            (match_id,),
        )
        conn.execute(
            """
            UPDATE league_ges_result_queue
            SET away_goals=2, updated_at=CURRENT_TIMESTAMP
            WHERE source_message_id=?
              AND home_team='Ajax' AND away_team='Feyenoord'
              AND home_goals=2 AND away_goals=0
            """,
            (source_id,),
        )
        if not conn.execute(
            """
            SELECT 1 FROM league_goal_events
            WHERE source_message_id=? AND team='Feyenoord'
              AND LOWER(player) LIKE '%van hooijdonk%'
            LIMIT 1
            """,
            (source_id,),
        ).fetchone():
            conn.execute(
                """
                INSERT INTO league_goal_events
                    (source_message_id, player, team, goals, confidence)
                VALUES (?, 'Van Hooijdonk', 'Feyenoord', 1, 1.0)
                """,
                (source_id,),
            )
        conn.commit()
        print(
            'AJPA correction: Ajax 2-2 Feyenoord repaired '
            f'source={source_id} • Rosales • Mitea • Van Hooijdonk • 1 Feyenoord goal pending'
        )
        return {
            'source_id': source_id,
            'source_channel_id': int(match['source_channel_id']),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _refresh_ges_card(guild: discord.Guild, source_id: int):
    row = ges._find(APP, guild.id, source=source_id)
    if not row or not row['ges_message_id'] or not row['ges_channel_id']:
        return
    try:
        channel = guild.get_channel(int(row['ges_channel_id']))
        if channel is None:
            channel = await BOT.fetch_channel(int(row['ges_channel_id']))
        if not hasattr(channel, 'fetch_message'):
            return
        message = await channel.fetch_message(int(row['ges_message_id']))
        embed = ges._embed(guild, row, row['status_by'])
        if message.attachments:
            embed.set_image(url=message.attachments[0].url)
        await message.edit(
            embed=embed,
            view=ges.GesView(str(row['status'] or 'PENDIENTE')),
        )
    except Exception as exc:
        print(
            f"WARNING AJPA Ajax-Feyenoord GES refresh guild={guild.id}: "
            f"{type(exc).__name__}: {exc}"
        )


async def _fix_on_ready():
    if APP is None or BOT is None:
        return

    for guild in list(BOT.guilds):
        try:
            changed = _apply_fix(APP, guild.id)
            if not changed:
                continue
            await league.refresh(APP, BOT, guild.id)
            await _refresh_ges_card(guild, int(changed['source_id']))

            # One-time visible correction in the original result channel. The DB
            # predicate becomes false after the repair, so restarts cannot repost it.
            channel = guild.get_channel(int(changed['source_channel_id']))
            if channel is None:
                try:
                    channel = await BOT.fetch_channel(int(changed['source_channel_id']))
                except Exception:
                    channel = None
            if channel is not None and hasattr(channel, 'send'):
                await channel.send(
                    '🛠️ **RESULTADO CORREGIDO**\n'
                    '**Ajax 2–2 Feyenoord**\n'
                    '⚽ Ajax: Rosales, Mitea\n'
                    '⚽ Feyenoord: Van Hooijdonk + 1 gol pendiente de atribuir\n'
                    'El marcador anterior 2–0 fue una lectura incorrecta de las filas 1er/2do.'
                )
        except Exception as exc:
            print(
                f"WARNING AJPA Ajax-Feyenoord correction guild={getattr(guild, 'id', '?')}: "
                f"{type(exc).__name__}: {exc}"
            )


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, '_ajpa_known_ajax_feyenoord_2_2_fix', False):
        return
    if not getattr(bot, '_ajpa_known_ajax_feyenoord_2_2_listener', False):
        bot.add_listener(_fix_on_ready, 'on_ready')
        bot._ajpa_known_ajax_feyenoord_2_2_listener = True
    runtime._ajpa_known_ajax_feyenoord_2_2_fix = True
    print('AJPA correction armed: Ajax 2-2 Feyenoord misread repair')


_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    '_ajpa_known_ajax_feyenoord_2_2_wrapper',
    False,
):
    _apply._ajpa_known_ajax_feyenoord_2_2_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
