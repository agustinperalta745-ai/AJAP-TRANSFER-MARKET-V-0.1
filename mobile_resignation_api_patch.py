"""Secure club resignation endpoint for AJPA Mobile.

The mobile action changes the authoritative AJPA assignment and audit trail
without deleting or moving the club roster/economy. It also writes a durable
Discord outbox event in the same transaction so the bot can publish the vacancy
after the HTTP request has finished.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_read_api
import mobile_write_api


def _ensure_history(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS club_assignment_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            club TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def ensure_discord_outbox(conn: sqlite3.Connection) -> None:
    """Create the durable queue used to bridge mobile resignations to Discord."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mobile_resignation_discord_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            club TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            next_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME
        );

        CREATE INDEX IF NOT EXISTS idx_mobile_resignation_outbox_pending
        ON mobile_resignation_discord_outbox(status, next_attempt_at, id);
        """
    )


def _resign(conn: sqlite3.Connection, session: dict) -> dict:
    club = mobile_write_api._require_club(conn, session)
    user_id = int(session["user_id"])

    row = conn.execute(
        "SELECT name FROM clubs WHERE user_id=? LIMIT 1",
        (user_id,),
    ).fetchone()
    if not row:
        raise mobile_write_api.ApiFailure(
            "Tu cuenta ya no tiene un club asignado.", HTTPStatus.CONFLICT
        )

    current = str(row["name"])
    if current.casefold() != str(club).casefold():
        raise mobile_write_api.ApiFailure(
            "La asignación cambió. Actualizá la app antes de renunciar.",
            HTTPStatus.CONFLICT,
        )

    cur = conn.execute(
        "DELETE FROM clubs WHERE user_id=? AND name=? COLLATE NOCASE",
        (user_id, current),
    )
    if cur.rowcount != 1:
        raise mobile_write_api.ApiFailure(
            "La asignación cambió mientras se procesaba la renuncia.",
            HTTPStatus.CONFLICT,
        )

    _ensure_history(conn)
    conn.execute(
        """
        INSERT INTO club_assignment_history(user_id, club, action, actor_id)
        VALUES(?, ?, 'RENUNCIA_DT', ?)
        """,
        (user_id, current, user_id),
    )

    # Queue Discord publication in the very same DB transaction. If the API
    # commit succeeds, the event cannot be lost just because Discord is
    # temporarily disconnected or the public channel is unavailable.
    ensure_discord_outbox(conn)
    conn.execute(
        """
        INSERT INTO mobile_resignation_discord_outbox(user_id, club)
        VALUES(?, ?)
        """,
        (user_id, current),
    )

    return {
        "ok": True,
        "club": current,
        "message": f"Renunciaste al cargo de DT de {current}. El club quedó libre.",
    }


def apply_mobile_resignation_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_resignation_patch", False):
        return

    original_post = handler.do_POST

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/me/resign":
            return original_post(self)

        conn = None
        try:
            # Consume the JSON payload (normally {}) so the handler behaves like
            # every other authenticated mutation route.
            mobile_write_api._read_json(self)
            conn = mobile_write_api.write_db()
            mobile_write_api.ensure_schema(conn)
            session = mobile_write_api._session(self.headers, conn)
            result = _resign(conn, session)
            conn.commit()
            self._json(result, HTTPStatus.OK)
        except mobile_write_api.ApiFailure as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"AJPA mobile resignation error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudo completar la renuncia."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        finally:
            if conn is not None:
                conn.close()

    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_resignation_patch = True
    print("AJPA Mobile: club resignation endpoint enabled")
