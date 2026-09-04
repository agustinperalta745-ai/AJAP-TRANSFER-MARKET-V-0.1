"""Expose official Liga match history through the existing mobile Liga payload.

The mobile client already reads standings and scorers from `/api/v1/league`.
This patch extends that same read-only payload with `matches`, sourced directly
from `league_matches`, so the app and Discord history always share one source of
truth. No result is copied or mutated here.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
import sqlite3
import unicodedata

import mobile_parity_api_patch as parity
import mobile_read_api


# Historical OCR/manual spellings that must resolve to one live club. Keep this
# deliberately small: it is only for known unambiguous club-name variants.
_MOBILE_HISTORY_TEAM_ALIASES = {
    "fullam": "fulham",
}


def _team_key(raw: str) -> str:
    value = unicodedata.normalize("NFKD", str(raw or "").strip().casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    if not value:
        return ""

    parts = value.split()
    # Club suffix/prefixes are presentation details and have historically
    # varied between JSON rosters, OCR results and old DB rows.
    while parts and parts[0] in {"fc", "cf"}:
        parts.pop(0)
    while parts and parts[-1] in {"fc", "cf"}:
        parts.pop()
    key = " ".join(parts)
    return _MOBILE_HISTORY_TEAM_ALIASES.get(key, key)


def _canonical_mobile_team(conn: sqlite3.Connection, raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return value

    wanted = _team_key(value)
    for canonical in mobile_read_api._live_mobile_club_names(conn):
        candidates = mobile_read_api._candidate_db_club_names(canonical)
        if any(_team_key(candidate) == wanted for candidate in candidates):
            return canonical
    return value


def _parse_time(raw) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _classic_periods(conn: sqlite3.Connection) -> list[dict]:
    """Load the historical intervals in which each classic rivalry was valid."""
    if "classic_rivals" not in parity._tables(conn):
        return []

    cols = mobile_read_api._columns(conn, "classic_rivals")
    if not {"club_a", "club_b"}.issubset(cols):
        return []

    accepted = "accepted_at" if "accepted_at" in cols else "NULL AS accepted_at"
    released = "released_at" if "released_at" in cols else "NULL AS released_at"
    active = "active" if "active" in cols else "1 AS active"
    rows = conn.execute(
        f"""
        SELECT club_a, club_b, {accepted}, {released}, {active}
        FROM classic_rivals
        ORDER BY id DESC
        """
    ).fetchall()
    return [
        {
            "club_a": str(row["club_a"] or ""),
            "club_b": str(row["club_b"] or ""),
            "accepted_at": _parse_time(row["accepted_at"]),
            "released_at": _parse_time(row["released_at"]),
            "active": bool(row["active"]),
        }
        for row in rows
    ]


def _is_classic_at(periods: list[dict], home: str, away: str, created_at) -> bool:
    """Return True only when this fixture happened during a classic interval."""
    home_key = _team_key(home)
    away_key = _team_key(away)
    played_at = _parse_time(created_at)
    if not home_key or not away_key:
        return False

    for period in periods:
        club_a = _team_key(period["club_a"])
        club_b = _team_key(period["club_b"])
        same_pair = (
            (home_key == club_a and away_key == club_b)
            or (home_key == club_b and away_key == club_a)
        )
        if not same_pair:
            continue

        accepted_at = period["accepted_at"]
        released_at = period["released_at"]
        if played_at is None:
            # Old rows without a timestamp cannot be placed in a closed historic
            # interval safely. They can still be marked for a currently active pair.
            if period["active"] and released_at is None:
                return True
            continue
        if accepted_at is not None and played_at < accepted_at:
            continue
        if released_at is not None and played_at > released_at:
            continue
        return True
    return False


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
    classics = _classic_periods(conn)

    return [
        {
            "id": int(row["id"]),
            "home_team": _canonical_mobile_team(conn, row["home_team"]),
            "away_team": _canonical_mobile_team(conn, row["away_team"]),
            "home_goals": int(row["home_goals"]),
            "away_goals": int(row["away_goals"]),
            "created_at": str(row["created_at"] or ""),
            "is_classic": _is_classic_at(
                classics,
                str(row["home_team"]),
                str(row["away_team"]),
                row["created_at"],
            ),
        }
        for row in rows
    ]


# Four historical test cards rejected by the owner. Match source IDs exactly so
# future Betis/Sevilla results, including another 2-0, remain visible.
HIDDEN_RESULT_CARD_SOURCE_IDS = frozenset({
    "1543407517021896744",
    "1543406316846981231",
    "1543372234897236039",
    "1543370690369949697",
})


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
    classics = _classic_periods(conn)
    return [dict(
        id=str(row["source_message_id"]),
        home_team=_canonical_mobile_team(conn, row["home_team"]),
        away_team=_canonical_mobile_team(conn, row["away_team"]),
        home_goals=int(row["home_goals"]), away_goals=int(row["away_goals"]),
        created_at=str(row["created_at"] or ""),
        is_classic=_is_classic_at(
            classics,
            str(row["home_team"]),
            str(row["away_team"]),
            row["created_at"],
        ),
    ) for row in rows if str(row["source_message_id"]) not in HIDDEN_RESULT_CARD_SOURCE_IDS]


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
