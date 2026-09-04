"""One-time checkpoint for the four verified Liga matches received while intake was paused.

This patch is deliberately additive and idempotent:
- it only targets the legacy AJPA guild while Pretemporada is active;
- it never deletes an existing official match;
- if an exact verified result already exists, it reuses that row instead of duplicating it;
- scorer rows for these four fully verified screenshots are replaced with the audited list;
- after the checkpoint, Discord standings are refreshed and the mobile app sees the same DB immediately.

The four screenshots were supplied by Staff after the 56-match checkpoint, so after a healthy
pre-pause DB this leaves Pretemporada at 60 official matches.
"""
from __future__ import annotations

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import competition_cycle as cycle
import league_authoritative_audit_reconcile_patch as audit

APP = None
BOT = None
TARGET_GUILD_ID = int(guild_isolation.LEGACY_GUILD_ID)
MARKER = "post_pause_verified_results_checkpoint_60_2026_09_03_v1"
SYNTHETIC_BASE = -202609039000

# (home, away, home_goals, away_goals, [(player, team, goals)])
VERIFIED_RESULTS = [
    (
        "Porto", "Fulham", 1, 0,
        [("Hélder Postiga", "Porto", 1)],
    ),
    (
        "Fiorentina", "París Saint-Germain (PSG)", 2, 2,
        [
            ("Mutu", "Fiorentina", 1),
            ("Toni", "Fiorentina", 1),
            ("Paulo César", "París Saint-Germain (PSG)", 1),
            ("P.A. Frau", "París Saint-Germain (PSG)", 1),
        ],
    ),
    (
        "Fiorentina", "Manchester City", 2, 2,
        [
            ("Santana", "Fiorentina", 1),
            ("Toni", "Fiorentina", 1),
            ("Vassel", "Manchester City", 1),
            ("Beasley", "Manchester City", 1),
        ],
    ),
    (
        "Manchester City", "Fiorentina", 2, 1,
        [
            ("Reyna", "Manchester City", 1),
            ("Dabo", "Manchester City", 1),
            ("Santana", "Fiorentina", 1),
        ],
    ),
]


def _table(conn, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone())


def _cols(conn, table: str) -> set[str]:
    if not _table(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _ensure_schema(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS league_post_pause_checkpoint_state (
            marker TEXT PRIMARY KEY,
            competition_id INTEGER NOT NULL,
            match_count_after INTEGER NOT NULL,
            applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            note TEXT
        )
    """)
    conn.commit()


def _active_preseason(conn):
    cycle.ensure_schema(conn)
    row = conn.execute(
        "SELECT phase,competition_id FROM competition_cycle_state WHERE id=1 LIMIT 1"
    ).fetchone()
    if not row or str(row["phase"] or "") != cycle.PRESEASON or row["competition_id"] is None:
        return None
    return int(row["competition_id"])


def _find_exact(conn, cid: int, home: str, away: str, hg: int, ag: int):
    cols = _cols(conn, "league_matches")
    if "competition_id" in cols:
        return conn.execute("""
            SELECT * FROM league_matches
            WHERE competition_id=? AND home_team=? AND away_team=?
              AND home_goals=? AND away_goals=?
            ORDER BY id DESC LIMIT 1
        """, (int(cid), home, away, int(hg), int(ag))).fetchone()
    return conn.execute("""
        SELECT * FROM league_matches
        WHERE home_team=? AND away_team=? AND home_goals=? AND away_goals=?
        ORDER BY id DESC LIMIT 1
    """, (home, away, int(hg), int(ag))).fetchone()


def _insert_match(conn, cid: int, index: int, home: str, away: str, hg: int, ag: int):
    source_id = SYNTHETIC_BASE - int(index)
    match_cols = _cols(conn, "league_matches")
    if "competition_id" in match_cols:
        conn.execute("""
            INSERT INTO league_matches(
                source_message_id,source_channel_id,author_id,
                home_team,away_team,home_goals,away_goals,
                confidence,created_at,competition_id
            ) VALUES(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,?)
        """, (source_id, 0, 0, home, away, int(hg), int(ag), 1.0, int(cid)))
    else:
        conn.execute("""
            INSERT INTO league_matches(
                source_message_id,source_channel_id,author_id,
                home_team,away_team,home_goals,away_goals,
                confidence,created_at
            ) VALUES(?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        """, (source_id, 0, 0, home, away, int(hg), int(ag), 1.0))
    return conn.execute(
        "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
        (source_id,),
    ).fetchone()


def _replace_verified_scorers(conn, cid: int, source_id: int, scorers) -> None:
    if not _table(conn, "league_goal_events"):
        return
    goal_cols = _cols(conn, "league_goal_events")
    conn.execute("DELETE FROM league_goal_events WHERE source_message_id=?", (int(source_id),))
    for player, team, goals in scorers:
        player = audit._normalize_player_name(conn, player)
        if "competition_id" in goal_cols:
            conn.execute("""
                INSERT INTO league_goal_events(
                    source_message_id,player,team,goals,confidence,created_at,competition_id
                ) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP,?)
            """, (int(source_id), player, team, int(goals), 1.0, int(cid)))
        else:
            conn.execute("""
                INSERT INTO league_goal_events(
                    source_message_id,player,team,goals,confidence,created_at
                ) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
            """, (int(source_id), player, team, int(goals), 1.0))


def _apply_checkpoint(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        cid = _active_preseason(conn)
        if cid is None:
            print("AJAP checkpoint 60: skipped because active phase is not Pretemporada")
            return False, None, None

        state = conn.execute(
            "SELECT * FROM league_post_pause_checkpoint_state WHERE marker=? LIMIT 1",
            (MARKER,),
        ).fetchone()
        if state:
            return False, cid, int(state["match_count_after"])

        conn.execute("BEGIN IMMEDIATE")
        touched = []
        for index, (home, away, hg, ag, scorers) in enumerate(VERIFIED_RESULTS, 1):
            row = _find_exact(conn, cid, home, away, hg, ag)
            if row is None:
                row = _insert_match(conn, cid, index, home, away, hg, ag)
            source_id = int(row["source_message_id"])
            _replace_verified_scorers(conn, cid, source_id, scorers)
            touched.append(source_id)

        match_cols = _cols(conn, "league_matches")
        if "competition_id" in match_cols:
            count = int(conn.execute(
                "SELECT COUNT(*) AS n FROM league_matches WHERE competition_id=?",
                (int(cid),),
            ).fetchone()["n"])
        else:
            count = int(conn.execute("SELECT COUNT(*) AS n FROM league_matches").fetchone()["n"])

        conn.execute("""
            INSERT INTO league_post_pause_checkpoint_state(
                marker,competition_id,match_count_after,note
            ) VALUES(?,?,?,?)
        """, (
            MARKER,
            int(cid),
            int(count),
            "4 resultados y 11 goles individuales verificados por Staff durante la pausa del lector; checkpoint esperado: 60 partidos.",
        ))
        conn.commit()
        print(
            f"AJAP checkpoint 60 applied: guild={guild_id} competition={cid} "
            f"matches={count} sources={touched}"
        )
        return True, cid, count
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


async def _run_checkpoint():
    if APP is None or BOT is None:
        return
    guild = BOT.get_guild(TARGET_GUILD_ID)
    if guild is None:
        return
    try:
        changed, _cid, count = _apply_checkpoint(APP, guild.id)
        if changed:
            try:
                await league.refresh(APP, BOT, guild.id)
            except Exception as exc:
                print(f"WARNING AJAP checkpoint 60 table refresh: {type(exc).__name__}: {exc}")
        if count is not None and count < 60:
            print(
                f"WARNING AJAP checkpoint 60: DB has only {count} matches after backfill; "
                "reader stays active but historical reconciliation should be reviewed."
            )
    except Exception as exc:
        print(f"ERROR AJAP checkpoint 60: {type(exc).__name__}: {exc}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_post_pause_checkpoint_60", False):
        return
    if not getattr(bot, "_ajap_post_pause_checkpoint_60_listener", False):
        bot.add_listener(_run_checkpoint, "on_ready")
        bot._ajap_post_pause_checkpoint_60_listener = True
    runtime._ajap_post_pause_checkpoint_60 = True
    print("AJAP checkpoint 60 armed: 4 paused results + verified scorers")


_PREVIOUS = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _PREVIOUS(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_post_pause_checkpoint_60_wrapper", False):
    _apply._ajap_post_pause_checkpoint_60_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
