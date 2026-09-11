"""Authoritative AJPA club unassignment + mobile access revocation.

This module contains no Discord network I/O so the same transaction can be used
from the HTTP API, Discord listeners and startup reconciliation.
"""

from __future__ import annotations

import sqlite3
import time


INACTIVE_ACTION = "DESVINCULADO_ADMIN"


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
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def ensure_assignment_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS club_assignment_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            club TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS club_assignment_guard (
            user_id INTEGER PRIMARY KEY,
            club TEXT,
            active INTEGER NOT NULL DEFAULT 0,
            revision INTEGER NOT NULL DEFAULT 1,
            source TEXT NOT NULL,
            actor_id INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS club_assignment_guard_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            observed_club TEXT,
            protected_club TEXT,
            action TEXT NOT NULL,
            railway_project_id TEXT,
            railway_service_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS club_unassignment_discord_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            club TEXT NOT NULL,
            source TEXT NOT NULL,
            actor_id INTEGER,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_error TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME
        );
        CREATE INDEX IF NOT EXISTS idx_club_unassignment_outbox_pending
            ON club_unassignment_discord_outbox(status, next_attempt_at, id);
        """
    )


def _candidate_club(conn: sqlite3.Connection, user_id: int) -> str | None:
    row = conn.execute(
        "SELECT name FROM clubs WHERE user_id=? LIMIT 1",
        (int(user_id),),
    ).fetchone()
    if row:
        club = str(row["name"] or "").strip()
        if club:
            return club

    if _table_exists(conn, "club_assignment_guard"):
        row = conn.execute(
            "SELECT club, active FROM club_assignment_guard WHERE user_id=? LIMIT 1",
            (int(user_id),),
        ).fetchone()
        if row and bool(row["active"]):
            club = str(row["club"] or "").strip() or None
            if club:
                return club

    if _table_exists(conn, "club_assignment_history"):
        row = conn.execute(
            """
            SELECT club, action
            FROM club_assignment_history
            WHERE user_id=?
            ORDER BY id DESC LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
        if row and str(row["action"] or "").strip().upper() in {
            "ASIGNADO",
            "ASIGNADO_VACANTE_ADMIN",
        }:
            club = str(row["club"] or "").strip() or None
            if club:
                return club
    return None


def revoke_mobile_access(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    preserve_staff: bool = True,
) -> dict:
    """Revoke DT Mobile credentials while optionally preserving Staff access.

    Club unassignment must remove a normal manager's app access, but a Staff/admin
    account is allowed to use AJPA Mobile without owning a club. Discord departure
    passes ``preserve_staff=False`` so leaving the guild still revokes everything.
    """
    now = int(time.time())
    sessions = 0
    pair_codes = 0
    staff_sessions_preserved = 0
    staff_pair_codes_preserved = 0

    if _table_exists(conn, "mobile_sessions"):
        has_staff = "is_staff" in _columns(conn, "mobile_sessions")
        if preserve_staff and has_staff:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM mobile_sessions
                WHERE user_id=? AND revoked_at IS NULL AND COALESCE(is_staff, 0)=1
                """,
                (int(user_id),),
            ).fetchone()
            staff_sessions_preserved = int(row["n"] if row else 0)
            cur = conn.execute(
                """
                UPDATE mobile_sessions
                SET revoked_at=?
                WHERE user_id=? AND revoked_at IS NULL AND COALESCE(is_staff, 0)=0
                """,
                (now, int(user_id)),
            )
        else:
            cur = conn.execute(
                """
                UPDATE mobile_sessions
                SET revoked_at=?
                WHERE user_id=? AND revoked_at IS NULL
                """,
                (now, int(user_id)),
            )
        sessions = max(0, int(cur.rowcount or 0))

    if _table_exists(conn, "mobile_pair_codes"):
        has_staff = "is_staff" in _columns(conn, "mobile_pair_codes")
        if preserve_staff and has_staff:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM mobile_pair_codes
                WHERE user_id=? AND used_at IS NULL AND COALESCE(is_staff, 0)=1
                """,
                (int(user_id),),
            ).fetchone()
            staff_pair_codes_preserved = int(row["n"] if row else 0)
            cur = conn.execute(
                """
                UPDATE mobile_pair_codes
                SET used_at=COALESCE(used_at, ?)
                WHERE user_id=? AND used_at IS NULL AND COALESCE(is_staff, 0)=0
                """,
                (now, int(user_id)),
            )
        else:
            cur = conn.execute(
                """
                UPDATE mobile_pair_codes
                SET used_at=COALESCE(used_at, ?)
                WHERE user_id=? AND used_at IS NULL
                """,
                (now, int(user_id)),
            )
        pair_codes = max(0, int(cur.rowcount or 0))

    return {
        "sessions_revoked": sessions,
        "pair_codes_revoked": pair_codes,
        "staff_sessions_preserved": staff_sessions_preserved,
        "staff_pair_codes_preserved": staff_pair_codes_preserved,
        "staff_access_preserved": bool(
            staff_sessions_preserved or staff_pair_codes_preserved
        ),
    }


def unassign_user_in_conn(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    actor_id: int | None = None,
    source: str = "ADMIN",
    queue_discord: bool = False,
) -> dict:
    """Free the club and make the inactive history authoritative.

    Normal DT Mobile credentials are revoked. Staff credentials remain valid when
    only the club assignment is removed, because Staff can use the app without a
    club. A real Discord departure revokes every credential.

    The operation is idempotent. The caller owns commit/rollback.
    """
    user_id = int(user_id)
    actor = int(actor_id) if actor_id is not None else None
    source = (str(source or "ADMIN").strip().upper() or "ADMIN")[:80]

    ensure_assignment_schema(conn)
    club = _candidate_club(conn, user_id)

    # Removing a club must not lock Staff out of AJPA Mobile. A real guild
    # departure is different: it invalidates both DT and Staff credentials.
    mobile = revoke_mobile_access(
        conn,
        user_id,
        preserve_staff=not source.startswith("DISCORD_LEFT"),
    )

    if not club:
        conn.execute("DELETE FROM clubs WHERE user_id=?", (user_id,))
        return {
            "ok": True,
            "user_id": user_id,
            "club": None,
            "changed": False,
            **mobile,
        }

    conn.execute("DELETE FROM clubs WHERE user_id=?", (user_id,))
    conn.execute(
        """
        INSERT INTO club_assignment_history(user_id, club, action, actor_id)
        VALUES(?, ?, ?, ?)
        """,
        (user_id, club, INACTIVE_ACTION, actor),
    )
    conn.execute(
        """
        INSERT INTO club_assignment_guard
            (user_id, club, active, revision, source, actor_id, updated_at)
        VALUES(?, ?, 0, 1, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            club=excluded.club,
            active=0,
            revision=club_assignment_guard.revision+1,
            source=excluded.source,
            actor_id=excluded.actor_id,
            updated_at=CURRENT_TIMESTAMP
        """,
        (user_id, club, f"UNASSIGN_{source}", actor),
    )
    conn.execute(
        """
        INSERT INTO club_assignment_guard_events
            (user_id, observed_club, protected_club, action)
        VALUES(?, ?, NULL, ?)
        """,
        (user_id, club, f"LEGITIMATE_UNASSIGN_{source}"),
    )

    if queue_discord:
        conn.execute(
            """
            INSERT INTO club_unassignment_discord_outbox
                (user_id, club, source, actor_id)
            VALUES(?, ?, ?, ?)
            """,
            (user_id, club, source, actor),
        )

    return {
        "ok": True,
        "user_id": user_id,
        "club": club,
        "changed": True,
        **mobile,
    }
