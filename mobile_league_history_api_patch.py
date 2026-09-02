"""Expose official Liga match history through the existing mobile Liga payload.

The mobile client already reads standings and scorers from `/api/v1/league`.
This patch extends that same read-only payload with `matches`, sourced directly
from `league_matches`, so the app and Discord history always share one source of
truth. No result is copied or mutated here.
"""

from __future__ import annotations

import sqlite3

import mobile_parity_api_patch as parity
import mobile_read_api


def _canonical_mobile_team(conn: sqlite3.Connection, raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return value
    wanted = value.casefold()
    for canonical in mobile_read_api._live_mobile_club_names(conn):
        candidates = mobile_read_api._candidate_db_club_names(canonical)
        if any(str(candidate).strip().casefold() == wanted for candidate in candidates):
            return canonical
    return value


def matches_payload(conn: sqlite3.Connection) -> list[dict]:
    if "league_matches" not in parity._tables(conn):
        return []

    cols = mobile_read_api._columns(conn, "league_matches")
    required = {"id", "home_team", "away_team", "home_goals", "away_goals"}
    if not required.issubset(cols):
        return []

    created = "created_at" if "created_at" in cols else "NULL AS created_at"
    rows = conn.execute(
        f"""
        SELECT id, home_team, away_team, home_goals, away_goals, {created}
        FROM league_matches
        ORDER BY id DESC
        LIMIT 500
        """
    ).fetchall()

    return [
        {
            "id": int(row["id"]),
            "home_team": _canonical_mobile_team(conn, row["home_team"]),
            "away_team": _canonical_mobile_team(conn, row["away_team"]),
            "home_goals": int(row["home_goals"]),
            "away_goals": int(row["away_goals"]),
            "created_at": str(row["created_at"] or ""),
        }
        for row in rows
    ]


def result_cards_payload(conn: sqlite3.Connection) -> list[dict]:
    """Closed results posted by the bot, including pending GES entries."""
    if "league_ges_result_queue" not in parity._tables(conn):
        return matches_payload(conn)
    rows = conn.execute(
        """SELECT source_message_id, home_team, away_team, home_goals,
                  away_goals, created_at
           FROM league_ges_result_queue WHERE ges_message_id IS NOT NULL
           ORDER BY created_at DESC, source_message_id DESC LIMIT 500"""
    ).fetchall()
    return [dict(
        id=str(row["source_message_id"]),
        home_team=_canonical_mobile_team(conn, row["home_team"]),
        away_team=_canonical_mobile_team(conn, row["away_team"]),
        home_goals=int(row["home_goals"]), away_goals=int(row["away_goals"]),
        created_at=str(row["created_at"] or ""),
    ) for row in rows]


def apply_mobile_league_history_api_patch() -> None:
    current = parity.league_payload
    if getattr(current, "_ajpa_mobile_league_history", False):
        return

    def league_payload_with_history(conn: sqlite3.Connection) -> dict:
        payload = dict(current(conn))
        payload["matches"] = matches_payload(conn)
        payload["result_cards"] = result_cards_payload(conn)
        return payload

    league_payload_with_history._ajpa_mobile_league_history = True
    league_payload_with_history._ajpa_mobile_league_history_base = current
    parity.league_payload = league_payload_with_history
