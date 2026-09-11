"""Compact latest-honours feed for the AJPA Mobile home screen.

The home screen only needs three tiny pieces of historical information:
- the latest finished league/preseason champion,
- that same competition's Golden Boot/top scorer,
- the latest finished cup champion.

Competition snapshots are the authority so starting a new season never changes an
old champion. Manager attribution is resolved as-of the competition close time
from assignment history when possible; the live assignment is only a fallback.
"""

from __future__ import annotations

import json
import os
import sqlite3
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_club_profiles_api_patch as profiles
import mobile_read_api
import mobile_write_api


_ACTIVE_ASSIGNMENT_ACTIONS = {"ASIGNADO", "ASIGNADO_VACANTE_ADMIN"}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _load_snapshot(raw) -> list[dict]:
    if raw is None:
        return []
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _discord_username(conn: sqlite3.Connection, user_id: int | None, club: str) -> str:
    if user_id is None:
        return "Sin DT asignado"

    # Prefer the real Discord username, not the server display nickname.
    try:
        import run_bot

        runtime = getattr(run_bot, "runtime", None)
        bot = getattr(runtime, "bot", None)
        raw_guild = (
            os.getenv("AJPA_MOBILE_GUILD_ID")
            or os.getenv("DISCORD_GUILD_ID")
            or ""
        ).strip()
        guild = bot.get_guild(int(raw_guild)) if bot and raw_guild else None
        member = guild.get_member(int(user_id)) if guild else None
        if member:
            username = str(getattr(member, "name", "") or "").strip()
            if username:
                return username
    except Exception:
        pass

    # Fallback for a historical DT who may no longer be cached in Discord.
    try:
        stored = profiles._stored_discord_name(conn, int(user_id))
        if stored:
            suffix = f" | {club}"
            label = str(stored).strip()
            if label.casefold().endswith(suffix.casefold()):
                label = label[: -len(suffix)].rstrip()
            if label:
                return label
    except Exception:
        pass

    return f"Discord · {int(user_id)}"


def _manager_at(conn: sqlite3.Connection, club: str, closed_at: str | None) -> dict:
    user_id: int | None = None
    history_found = False
    tables = _tables(conn)

    if closed_at and "club_assignment_history" in tables:
        row = conn.execute(
            """
            SELECT user_id, action
            FROM club_assignment_history
            WHERE club=? COLLATE NOCASE AND created_at<=?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (club, closed_at),
        ).fetchone()
        if row:
            history_found = True
            if str(row["action"] or "").strip().upper() in _ACTIVE_ASSIGNMENT_ACTIONS:
                user_id = int(row["user_id"])

    # Old databases may not have a usable assignment-history row. Only in that
    # case use today's owner; never replace a known historical vacancy/change.
    if not history_found and user_id is None:
        owner = profiles._owner_row(conn, club)
        if owner and owner["user_id"] is not None:
            user_id = int(owner["user_id"])

    return {
        "user_id": str(user_id) if user_id is not None else None,
        "username": _discord_username(conn, user_id, club),
    }


def _latest_finished(conn: sqlite3.Connection, kinds: tuple[str, ...]):
    if "competition_editions" not in _tables(conn):
        return None
    placeholders = ",".join("?" for _ in kinds)
    return conn.execute(
        f"""
        SELECT id, kind, name, sequence, closed_at, standings_snapshot, scorers_snapshot
        FROM competition_editions
        WHERE status='FINISHED' AND kind IN ({placeholders})
        ORDER BY COALESCE(closed_at, started_at) DESC, id DESC
        LIMIT 1
        """,
        tuple(kinds),
    ).fetchone()


def _champion_payload(conn: sqlite3.Connection, edition) -> dict | None:
    if not edition:
        return None
    standings = _load_snapshot(edition["standings_snapshot"])
    if not standings:
        return None
    first = standings[0]
    team = str(first.get("team") or "").strip()
    if not team:
        return None
    return {
        "competition_id": int(edition["id"]),
        "competition": str(edition["name"]),
        "kind": str(edition["kind"]),
        "team": team,
        "manager": _manager_at(conn, team, str(edition["closed_at"] or "") or None),
    }


def _scorer_payload(conn: sqlite3.Connection, edition) -> dict | None:
    if not edition:
        return None
    scorers = _load_snapshot(edition["scorers_snapshot"])
    if not scorers:
        return None
    first = scorers[0]
    player = str(first.get("player") or "").strip()
    team = str(first.get("team") or "").strip()
    try:
        goals = int(first.get("goals") or 0)
    except (TypeError, ValueError):
        goals = 0
    if not player or not team:
        return None
    return {
        "competition_id": int(edition["id"]),
        "competition": str(edition["name"]),
        "player": player,
        "goals": goals,
        "team": team,
        "manager": _manager_at(conn, team, str(edition["closed_at"] or "") or None),
    }


def latest_honours_payload(conn: sqlite3.Connection) -> dict:
    # Until the first ordinary season closes, the finished preseason is the last
    # champion of AJPA and is intentionally shown. Cup history is independent.
    latest_league = _latest_finished(conn, ("SEASON", "PRESEASON"))
    latest_cup = _latest_finished(conn, ("CUP",))
    return {
        "season_champion": _champion_payload(conn, latest_league),
        "top_scorer": _scorer_payload(conn, latest_league),
        "cup_champion": _champion_payload(conn, latest_cup),
    }


def apply_mobile_latest_honours_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_latest_honours_patch", False):
        return

    original_get = handler.do_GET

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/league/latest-honours":
            return original_get(self)
        try:
            with mobile_write_api.write_db() as conn:
                self._json(latest_honours_payload(conn))
        except Exception as exc:
            print(f"AJPA latest honours GET error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudieron cargar los últimos campeones."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    handler.do_GET = get
    handler._ajpa_mobile_latest_honours_patch = True
    print("AJPA Mobile: últimos campeón/goleador/campeón de copa activos")
