"""Bounded repairs for two user-verified Ajax/Feyenoord OCR mistakes on 2026-09-04.

1) Ajax 2-0 Feyenoord was actually Ajax 2-2 Feyenoord.
   Keep Rosales + Mitea for Ajax, add verified Van Hooijdonk x1; one Feyenoord goal remains unattributed.
2) Feyenoord 1-1 Ajax was actually Feyenoord 0-2 Ajax.
   Huntelaar scored both Ajax goals.

The repair only runs when the current bad score + scorer fingerprint uniquely
identifies the affected source. It also updates the GES queue and refreshes the
standings/scorers, so the app and Discord derive from the corrected match row.
"""
from __future__ import annotations

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_persistent_result_correction_patch as persistent_tools

APP = None
BOT = None


def _tables(conn):
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _candidate(conn, home, away, hg, ag, required_players):
    rows = conn.execute(
        """
        SELECT m.*
        FROM league_matches m
        WHERE m.created_at >= '2026-09-04 00:00:00'
          AND m.created_at <  '2026-09-06 00:00:00'
          AND m.home_team=? AND m.away_team=?
          AND m.home_goals=? AND m.away_goals=?
        ORDER BY m.id DESC
        """,
        (home, away, int(hg), int(ag)),
    ).fetchall()
    good = []
    wanted = {p.casefold() for p in required_players}
    for row in rows:
        scorers = conn.execute(
            "SELECT player,team,goals FROM league_goal_events WHERE source_message_id=?",
            (int(row['source_message_id']),),
        ).fetchall()
        names = {str(s['player'] or '').strip().casefold() for s in scorers}
        if wanted.issubset(names):
            good.append(row)
    return good[0] if len(good) == 1 else None


def _update_queue(conn, source_id, hg, ag):
    if 'league_ges_result_queue' not in _tables(conn):
        return
    conn.execute(
        """
        UPDATE league_ges_result_queue
        SET home_goals=?, away_goals=?, updated_at=CURRENT_TIMESTAMP
        WHERE source_message_id=?
        """,
        (int(hg), int(ag), int(source_id)),
    )


def _repair_ajax_22(runtime, guild_id):
    conn = league.db(runtime, int(guild_id))
    try:
        row = _candidate(conn, 'Ajax', 'Feyenoord', 2, 0, ('Rosales', 'Mitea'))
        if not row:
            return None
        source = int(row['source_message_id'])
        conn.execute('BEGIN IMMEDIATE')
        conn.execute(
            'UPDATE league_matches SET home_goals=2, away_goals=2, confidence=1.0 WHERE source_message_id=?',
            (source,),
        )
        # Preserve verified Ajax scorers, clear any false Feyenoord attribution, then add the visible one.
        conn.execute(
            "DELETE FROM league_goal_events WHERE source_message_id=? AND COALESCE(team,'') COLLATE NOCASE='Feyenoord'",
            (source,),
        )
        exists = conn.execute(
            "SELECT 1 FROM league_goal_events WHERE source_message_id=? AND player='Van Hooijdonk' COLLATE NOCASE LIMIT 1",
            (source,),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO league_goal_events(source_message_id,player,team,goals,confidence) VALUES(?,?,?,?,1.0)",
                (source, 'Van Hooijdonk', 'Feyenoord', 1),
            )
        _update_queue(conn, source, 2, 2)
        conn.commit()
        print(f'AJAP repair: Ajax 2-2 Feyenoord source={source}; Rosales, Mitea, Van Hooijdonk; 1 FEY goal pending')
        return source
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _repair_feyenoord_02(runtime, guild_id):
    conn = league.db(runtime, int(guild_id))
    try:
        row = _candidate(conn, 'Feyenoord', 'Ajax', 1, 1, ('Huntelaar',))
        if not row:
            return None
        source = int(row['source_message_id'])
        conn.execute('BEGIN IMMEDIATE')
        conn.execute(
            'UPDATE league_matches SET home_goals=0, away_goals=2, confidence=1.0 WHERE source_message_id=?',
            (source,),
        )
        conn.execute('DELETE FROM league_goal_events WHERE source_message_id=?', (source,))
        conn.execute(
            "INSERT INTO league_goal_events(source_message_id,player,team,goals,confidence) VALUES(?,?,?,?,1.0)",
            (source, 'Huntelaar', 'Ajax', 2),
        )
        _update_queue(conn, source, 0, 2)
        conn.commit()
        print(f'AJAP repair: Feyenoord 0-2 Ajax source={source}; Huntelaar x2')
        return source
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _on_ready():
    if APP is None or BOT is None:
        return
    for guild in list(BOT.guilds):
        changed = []
        try:
            for fn in (_repair_ajax_22, _repair_feyenoord_02):
                source = fn(APP, guild.id)
                if source:
                    changed.append(source)
            if changed:
                await league.refresh(APP, BOT, guild.id)
        except Exception as exc:
            print(f'WARNING AJAP Ajax/Feyenoord repair guild={guild.id}: {type(exc).__name__}: {exc}')


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    # Always install the permanent Staff controls even if this bounded data repair
    # was already armed earlier in the same process.
    persistent_tools._install(runtime, bot)
    if getattr(bot, '_ajap_ajax_feyenoord_score_repairs', False):
        return
    bot.add_listener(_on_ready, 'on_ready')
    bot._ajap_ajax_feyenoord_score_repairs = True
    print('AJAP bounded repairs armed: Ajax/Feyenoord OCR mistakes')


_ORIGINAL = guild_isolation.apply_guild_isolation_patch


def _wrapped(runtime, bot):
    _ORIGINAL(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, '_ajap_ajax_feyenoord_score_repairs_wrapper', False):
    _wrapped._ajap_ajax_feyenoord_score_repairs_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _wrapped
