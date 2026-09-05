"""Bounded repairs for two user-verified Ajax/Feyenoord OCR mistakes on 2026-09-04.

1) The Rosales + Mitea match is Ajax 2-2 Feyenoord. Earlier OCR variants stored
   it as 2-0, 1-1, or even with the teams reversed. The scorer fingerprint keeps
   this repair isolated from the other fixture.
2) Feyenoord 1-1 Ajax with Huntelaar was actually Feyenoord 0-2 Ajax.
   Huntelaar scored both Ajax goals.

Repairs update league_matches, manual review metadata and GES queue, then refresh
standings/scorers so Discord and the app derive from the corrected row.
"""
from __future__ import annotations

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_persistent_result_correction_patch as persistent_tools

APP = None
BOT = None


def _tables(conn):
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _scorer_names(conn, source_id):
    rows = conn.execute(
        "SELECT player,team,goals FROM league_goal_events WHERE source_message_id=?",
        (int(source_id),),
    ).fetchall()
    return {str(row['player'] or '').strip().casefold() for row in rows}


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
    wanted = {p.casefold() for p in required_players}
    good = [row for row in rows if wanted.issubset(_scorer_names(conn, row['source_message_id']))]
    return good[0] if len(good) == 1 else None


def _ajax_22_candidate(conn):
    """Find the verified Rosales+Mitea 2-2 even if OCR stored score/orientation wrong."""
    rows = conn.execute(
        """
        SELECT m.*
        FROM league_matches m
        WHERE m.created_at >= '2026-09-04 00:00:00'
          AND m.created_at <  '2026-09-06 00:00:00'
          AND (
                (m.home_team='Ajax' AND m.away_team='Feyenoord')
             OR (m.home_team='Feyenoord' AND m.away_team='Ajax')
          )
          AND (
                (m.home_goals=2 AND m.away_goals=0)
             OR (m.home_goals=1 AND m.away_goals=1)
             OR (m.home_goals=0 AND m.away_goals=2)
             OR (m.home_goals=2 AND m.away_goals=2)
          )
        ORDER BY m.id DESC
        """
    ).fetchall()
    wanted = {'rosales', 'mitea'}
    good = [row for row in rows if wanted.issubset(_scorer_names(conn, row['source_message_id']))]
    return good[0] if len(good) == 1 else None


def _update_queue(conn, source_id, home, away, hg, ag):
    if 'league_ges_result_queue' not in _tables(conn):
        return
    conn.execute(
        """
        UPDATE league_ges_result_queue
        SET home_team=?, away_team=?, home_goals=?, away_goals=?, updated_at=CURRENT_TIMESTAMP
        WHERE source_message_id=?
        """,
        (str(home), str(away), int(hg), int(ag), int(source_id)),
    )


def _update_review(conn, source_id, home, away, hg, ag):
    if 'league_manual_reviews' not in _tables(conn):
        return
    conn.execute(
        """
        UPDATE league_manual_reviews
        SET home_team=?, away_team=?, home_goals=?, away_goals=?
        WHERE source_message_id=?
        """,
        (str(home), str(away), int(hg), int(ag), int(source_id)),
    )


def _repair_ajax_22(runtime, guild_id):
    conn = league.db(runtime, int(guild_id))
    try:
        row = _ajax_22_candidate(conn)
        if not row:
            return None
        source = int(row['source_message_id'])
        already_ok = (
            str(row['home_team']) == 'Ajax'
            and str(row['away_team']) == 'Feyenoord'
            and int(row['home_goals']) == 2
            and int(row['away_goals']) == 2
        )
        conn.execute('BEGIN IMMEDIATE')
        conn.execute(
            """
            UPDATE league_matches
            SET home_team='Ajax', away_team='Feyenoord',
                home_goals=2, away_goals=2, confidence=1.0
            WHERE source_message_id=?
            """,
            (source,),
        )
        # Preserve verified Ajax scorers. Remove only Feyenoord rows that are not
        # the visible Van Hooijdonk attribution; the second FEY goal stays pending.
        conn.execute(
            """
            DELETE FROM league_goal_events
            WHERE source_message_id=?
              AND COALESCE(team,'') COLLATE NOCASE='Feyenoord'
              AND player COLLATE NOCASE<>'Van Hooijdonk'
            """,
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
        # Ensure scorer team labels follow the corrected orientation.
        conn.execute(
            "UPDATE league_goal_events SET team='Ajax' WHERE source_message_id=? AND player IN ('Rosales','Mitea') COLLATE NOCASE",
            (source,),
        )
        _update_queue(conn, source, 'Ajax', 'Feyenoord', 2, 2)
        _update_review(conn, source, 'Ajax', 'Feyenoord', 2, 2)
        conn.commit()
        if not already_ok:
            print(f'AJAP repair: Ajax 2-2 Feyenoord source={source}; Rosales, Mitea, Van Hooijdonk; 1 FEY goal pending')
        return source if not already_ok else None
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
        _update_queue(conn, source, 'Feyenoord', 'Ajax', 0, 2)
        _update_review(conn, source, 'Feyenoord', 'Ajax', 0, 2)
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
