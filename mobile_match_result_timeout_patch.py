"""Expire matched AJPA mobile cards when no official result is detected in time.

The result bot remains the source of truth: before expiring a MATCHED card we
first reconcile against ``league_matches``. If a result exists, the card becomes
COMPLETED and keeps showing the final score. Otherwise the stale card becomes
EXPIRED and disappears from the mobile board.
"""

from __future__ import annotations

import os
import sqlite3

import mobile_match_search_patch


DEFAULT_RESULT_TIMEOUT_MINUTES = 120


def _timeout_minutes() -> int:
    raw = str(
        os.getenv(
            "AJPA_MATCH_RESULT_TIMEOUT_MINUTES",
            DEFAULT_RESULT_TIMEOUT_MINUTES,
        )
    ).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_RESULT_TIMEOUT_MINUTES
    return max(15, value)


def _expire_stale_matched(conn: sqlite3.Connection) -> None:
    """Complete matches with a detected result, then expire stale unresolved ones."""
    mobile_match_search_patch._reconcile_completed(conn)
    timeout = _timeout_minutes()
    conn.execute(
        """
        UPDATE mobile_match_searches
        SET status='EXPIRED', expired_at=CURRENT_TIMESTAMP
        WHERE status='MATCHED'
          AND matched_at IS NOT NULL
          AND result_home_goals IS NULL
          AND datetime(matched_at) <= datetime('now', ?)
        """,
        (f"-{timeout} minutes",),
    )


def apply_mobile_match_result_timeout_patch() -> None:
    if getattr(
        mobile_match_search_patch,
        "_ajpa_mobile_match_result_timeout_patch",
        False,
    ):
        return

    original_matched_search_for_club = (
        mobile_match_search_patch._matched_search_for_club
    )
    original_searches_payload = mobile_match_search_patch.searches_payload

    def matched_search_for_club(conn: sqlite3.Connection, club: str):
        _expire_stale_matched(conn)
        return original_matched_search_for_club(conn, club)

    def searches_payload(conn: sqlite3.Connection, session: dict | None) -> dict:
        _expire_stale_matched(conn)
        return original_searches_payload(conn, session)

    mobile_match_search_patch._matched_search_for_club = matched_search_for_club
    mobile_match_search_patch.searches_payload = searches_payload
    mobile_match_search_patch._ajpa_mobile_match_result_timeout_patch = True

    print(
        "AJPA Mobile: tarjetas MATCHED sin resultado expiran tras "
        f"{_timeout_minutes()} minutos"
    )
