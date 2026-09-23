"""Keep market_state and market_cycles synchronized.

The competitive phase is intentionally independent from the transfer market.
market_cycles only identifies each real open/close market window so rules such
as "one clausulazo per DT / seller / player per market" have a stable scope.
"""

from __future__ import annotations

import sqlite3


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {
        str(row["name"])
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def ensure_market_window_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER,
            opened_by INTEGER,
            opened_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            closed_by INTEGER,
            closed_at DATETIME,
            report_sent_at DATETIME,
            report_recipient_count INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    if _table_exists(conn, "market_state"):
        columns = _columns(conn, "market_state")
        if "updated_by" not in columns:
            conn.execute("ALTER TABLE market_state ADD COLUMN updated_by INTEGER")
        if "updated_at" not in columns:
            conn.execute(
                "ALTER TABLE market_state ADD COLUMN updated_at DATETIME"
            )


def _active_season_id(conn: sqlite3.Connection):
    if not _table_exists(conn, "seasons"):
        return None
    row = conn.execute(
        "SELECT id FROM seasons WHERE active=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def sync_market_window(
    conn: sqlite3.Connection,
    opened: bool,
    *,
    actor_id: int | None = None,
):
    """Make the active market window match market_state without touching phases."""
    ensure_market_window_schema(conn)

    active = conn.execute(
        "SELECT * FROM market_cycles WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()

    state = None
    if _table_exists(conn, "market_state"):
        state = conn.execute(
            "SELECT is_open, updated_by, updated_at FROM market_state WHERE id=1"
        ).fetchone()

    effective_actor = actor_id
    if effective_actor is None and state and state["updated_by"] is not None:
        effective_actor = int(state["updated_by"])
    if effective_actor is None:
        effective_actor = 0

    if opened:
        if active:
            return active

        opened_at = (
            str(state["updated_at"])
            if state and state["updated_at"]
            else None
        )
        if opened_at:
            cur = conn.execute(
                """
                INSERT INTO market_cycles(season_id,opened_by,opened_at)
                VALUES(?,?,?)
                """,
                (_active_season_id(conn), int(effective_actor), opened_at),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO market_cycles(season_id,opened_by)
                VALUES(?,?)
                """,
                (_active_season_id(conn), int(effective_actor)),
            )
        return conn.execute(
            "SELECT * FROM market_cycles WHERE id=?",
            (int(cur.lastrowid),),
        ).fetchone()

    if active:
        conn.execute(
            """
            UPDATE market_cycles
            SET closed_by=?, closed_at=CURRENT_TIMESTAMP
            WHERE id=? AND closed_at IS NULL
            """,
            (int(effective_actor), int(active["id"])),
        )
    return None


def active_market_window(conn: sqlite3.Connection):
    """Return the canonical current market window, repairing old desync safely."""
    opened = False
    if _table_exists(conn, "market_state"):
        row = conn.execute(
            "SELECT is_open FROM market_state WHERE id=1"
        ).fetchone()
        opened = bool(row and int(row["is_open"]))

    return sync_market_window(conn, opened)
