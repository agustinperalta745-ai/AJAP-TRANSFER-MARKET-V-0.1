"""One-time repair for legacy Season 1 data after the competition-cycle rollout.

The first cycle bootstrap tagged every pre-existing league match as `preseason`.
If Staff then started Temporada 1, those historical rows stayed attached to the
finished bootstrap preseason edition, so the new Season 1 table looked empty.

This repair never deletes matches, goal events, classic history, rosters,
finances or transfers. It only reassigns rows that demonstrably pre-date the
bootstrap edition into the real Temporada 1 competition.
"""

from __future__ import annotations

import sqlite3

import competition_cycle as cycle
import mobile_write_api

MIGRATION_KEY = "2026-09-02-restore-legacy-season1-from-bootstrap-preseason"


def _table(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
    )


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _migration_done(conn: sqlite3.Connection) -> bool:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ajpa_data_migrations (
            key TEXT PRIMARY KEY,
            applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            detail TEXT
        )
        """
    )
    return bool(
        conn.execute(
            "SELECT 1 FROM ajpa_data_migrations WHERE key=? LIMIT 1",
            (MIGRATION_KEY,),
        ).fetchone()
    )


def _mark_done(conn: sqlite3.Connection, detail: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO ajpa_data_migrations(key,detail) VALUES(?,?)",
        (MIGRATION_KEY, str(detail)),
    )


def _legacy_where(cols: set[str]) -> tuple[str, bool]:
    if "created_at" in cols:
        return (
            "competition_id=? AND (created_at IS NULL OR datetime(created_at)<=datetime(?))",
            True,
        )
    return ("competition_id=?", False)


def _count_legacy_rows(
    conn: sqlite3.Connection,
    table: str,
    bootstrap_id: int,
    bootstrap_started_at: str,
) -> int:
    cols = _cols(conn, table)
    if "competition_id" not in cols:
        return 0
    where, uses_date = _legacy_where(cols)
    params = (
        (int(bootstrap_id), str(bootstrap_started_at))
        if uses_date
        else (int(bootstrap_id),)
    )
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", params).fetchone()
    return int(row["c"] or 0) if row else 0


def _move_legacy_rows(
    conn: sqlite3.Connection,
    table: str,
    bootstrap_id: int,
    bootstrap_started_at: str,
    target_id: int,
) -> int:
    cols = _cols(conn, table)
    if "competition_id" not in cols:
        return 0
    where, uses_date = _legacy_where(cols)
    params = (
        (int(target_id), int(bootstrap_id), str(bootstrap_started_at))
        if uses_date
        else (int(target_id), int(bootstrap_id))
    )
    cur = conn.execute(
        f"UPDATE {table} SET competition_id=? WHERE {where}",
        params,
    )
    return max(0, int(cur.rowcount or 0))


def repair_conn(conn: sqlite3.Connection) -> dict:
    """Repair only the rollout bootstrap case; never remove user data."""
    conn.row_factory = sqlite3.Row
    cycle.ensure_schema(conn)

    if _migration_done(conn):
        return {"changed": False, "reason": "already_applied"}

    state = conn.execute(
        "SELECT phase,season_number,competition_id FROM competition_cycle_state WHERE id=1"
    ).fetchone()
    if not state or int(state["season_number"] or 0) != 1:
        return {"changed": False, "reason": "not_season_1"}

    bootstrap = conn.execute(
        """
        SELECT id,started_at,status
        FROM competition_editions
        WHERE kind='preseason' AND season_number=1
        ORDER BY id ASC LIMIT 1
        """
    ).fetchone()
    if not bootstrap:
        return {"changed": False, "reason": "no_bootstrap_preseason"}

    bootstrap_id = int(bootstrap["id"])
    bootstrap_started_at = str(bootstrap["started_at"] or "")
    legacy_matches = _count_legacy_rows(
        conn, "league_matches", bootstrap_id, bootstrap_started_at
    )
    legacy_goals = _count_legacy_rows(
        conn, "league_goal_events", bootstrap_id, bootstrap_started_at
    )
    if legacy_matches <= 0 and legacy_goals <= 0:
        return {"changed": False, "reason": "no_legacy_rows"}

    season = conn.execute(
        """
        SELECT id,status
        FROM competition_editions
        WHERE kind='season' AND season_number=1
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()

    if season:
        target_id = int(season["id"])
        moved_matches = _move_legacy_rows(
            conn, "league_matches", bootstrap_id, bootstrap_started_at, target_id
        )
        moved_goals = _move_legacy_rows(
            conn, "league_goal_events", bootstrap_id, bootstrap_started_at, target_id
        )

        if str(season["status"] or "") == "finished":
            conn.execute(
                "UPDATE competition_editions SET final_snapshot_json=? WHERE id=?",
                (cycle._snapshot(conn, target_id), target_id),
            )
        if str(bootstrap["status"] or "") == "finished":
            conn.execute(
                "UPDATE competition_editions SET final_snapshot_json=? WHERE id=?",
                (cycle._snapshot(conn, bootstrap_id), bootstrap_id),
            )

        detail = (
            f"moved matches={moved_matches}, goals={moved_goals}, "
            f"preseason={bootstrap_id} -> season={target_id}"
        )
        _mark_done(conn, detail)
        return {
            "changed": bool(moved_matches or moved_goals),
            "moved_matches": moved_matches,
            "moved_goals": moved_goals,
            "target_competition_id": target_id,
        }

    # If Staff has not yet pressed "Iniciar Temporada 1", keep the same
    # competition id and relabel the bootstrap edition as the already-running
    # Season 1. This preserves every existing result exactly where it is.
    if (
        str(state["phase"] or "") == cycle.PRESEASON
        and state["competition_id"] is not None
        and int(state["competition_id"]) == bootstrap_id
    ):
        conn.execute(
            """
            UPDATE competition_editions
            SET kind='season', label='Temporada 1', status='active', ended_at=NULL,
                final_snapshot_json=NULL
            WHERE id=?
            """,
            (bootstrap_id,),
        )
        conn.execute(
            """
            UPDATE competition_cycle_state
            SET phase='season', updated_at=CURRENT_TIMESTAMP
            WHERE id=1
            """
        )
        cycle._sync_season(conn, 1)
        detail = f"converted bootstrap competition {bootstrap_id} into Temporada 1"
        _mark_done(conn, detail)
        return {
            "changed": True,
            "converted_bootstrap": True,
            "target_competition_id": bootstrap_id,
        }

    return {"changed": False, "reason": "no_safe_target"}


def apply_bootstrap_repair() -> dict:
    conn = None
    try:
        conn = mobile_write_api.write_db()
        result = repair_conn(conn)
        conn.commit()
        if result.get("changed"):
            print(f"AJPA cycle repair: {result}")
        return result
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"AJPA cycle repair skipped safely: {type(exc).__name__}: {exc}")
        return {"changed": False, "error": type(exc).__name__}
    finally:
        if conn is not None:
            conn.close()
