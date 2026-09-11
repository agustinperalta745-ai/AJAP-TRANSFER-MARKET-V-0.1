"""Compact latest-honours feed for the AJPA Mobile home screen.

The home screen shows the last completed league/preseason champion, that same
competition's top scorer, and the last completed cup champion. The active
competition never replaces these cards until it has actually finished.

With the AJPA cycle this means:
- Temporada 1 shows Pretemporada.
- Temporada 2 shows Temporada 1.
- Temporada 3 shows Temporada 2, and so on.

Manager attribution is resolved as-of the competition close time from assignment
history when possible; the live assignment is only a fallback.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from http import HTTPStatus
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import mobile_club_profiles_api_patch as profiles
import mobile_read_api
import mobile_write_api


_ACTIVE_ASSIGNMENT_ACTIONS = {"ASIGNADO", "ASIGNADO_VACANTE_ADMIN"}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if table not in _tables(conn):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _snapshot(raw) -> dict:
    """Read both the current {standings, scorers} snapshot and old list snapshots."""
    if raw is None:
        return {"standings": [], "scorers": []}
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return {"standings": [], "scorers": []}
    if not isinstance(value, dict):
        return {"standings": [], "scorers": []}
    standings = value.get("standings")
    scorers = value.get("scorers")
    return {
        "standings": [item for item in standings if isinstance(item, dict)] if isinstance(standings, list) else [],
        "scorers": [item for item in scorers if isinstance(item, dict)] if isinstance(scorers, list) else [],
    }


def _legacy_list(raw) -> list[dict]:
    if raw is None:
        return []
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _clean_discord_name(value, club: str) -> str | None:
    """Return a human Discord name and never expose a raw snowflake/user id."""
    label = str(value or "").strip()
    if not label:
        return None
    suffix = f" | {club}"
    if label.casefold().endswith(suffix.casefold()):
        label = label[: -len(suffix)].rstrip()
    if not label or label.isdigit():
        return None
    return label


def _discord_rest_name(user_id: int, club: str) -> str | None:
    """Resolve a member name even when discord.py's member cache is unavailable."""
    raw_guild = (
        os.getenv("AJPA_MOBILE_GUILD_ID")
        or os.getenv("DISCORD_GUILD_ID")
        or ""
    ).strip()
    token = (
        os.getenv("DISCORD_TOKEN")
        or os.getenv("BOT_TOKEN")
        or os.getenv("DISCORD_BOT_TOKEN")
        or os.getenv("TOKEN")
        or ""
    ).strip()
    if not raw_guild or not token:
        return None

    request = Request(
        f"https://discord.com/api/v10/guilds/{int(raw_guild)}/members/{int(user_id)}",
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "AJPA-Mobile/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None

    user = payload.get("user") if isinstance(payload, dict) else None
    user = user if isinstance(user, dict) else {}
    for candidate in (
        payload.get("nick") if isinstance(payload, dict) else None,
        user.get("global_name"),
        user.get("username"),
    ):
        username = _clean_discord_name(candidate, club)
        if username:
            return username
    return None


def _discord_username(conn: sqlite3.Connection, user_id: int | None, club: str) -> str:
    if user_id is None:
        return "Sin DT asignado"

    # Prefer the local Discord cache when available.
    try:
        run_bot = sys.modules.get("run_bot")
        runtime = getattr(run_bot, "runtime", None) if run_bot else None
        bot = getattr(runtime, "bot", None)
        raw_guild = (
            os.getenv("AJPA_MOBILE_GUILD_ID")
            or os.getenv("DISCORD_GUILD_ID")
            or ""
        ).strip()
        guild = bot.get_guild(int(raw_guild)) if bot and raw_guild else None
        member = guild.get_member(int(user_id)) if guild else None
        if member:
            for candidate in (
                getattr(member, "display_name", None),
                getattr(member, "global_name", None),
                getattr(member, "name", None),
            ):
                username = _clean_discord_name(candidate, club)
                if username:
                    return username

        cached_user = bot.get_user(int(user_id)) if bot else None
        if cached_user:
            for candidate in (
                getattr(cached_user, "global_name", None),
                getattr(cached_user, "name", None),
            ):
                username = _clean_discord_name(candidate, club)
                if username:
                    return username
    except Exception:
        pass

    # The mobile HTTP server can start before Discord's member cache is ready.
    # Resolve the member directly from Discord so the app still shows the real DT.
    live_name = _discord_rest_name(int(user_id), club)
    if live_name:
        return live_name

    # Historical fallback stored by the nickname system.
    try:
        stored = profiles._stored_discord_name(conn, int(user_id))
        username = _clean_discord_name(stored, club)
        if username:
            return username
    except Exception:
        pass

    return "Nombre de Discord no disponible"


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
    cols = _columns(conn, "competition_editions")
    lowered = tuple(str(kind).lower() for kind in kinds)
    placeholders = ",".join("?" for _ in lowered)

    if {"label", "season_number", "ended_at", "final_snapshot_json"}.issubset(cols):
        return conn.execute(
            f"""
            SELECT id, kind, season_number, label, started_at, ended_at, final_snapshot_json
            FROM competition_editions
            WHERE LOWER(status)='finished' AND LOWER(kind) IN ({placeholders})
            ORDER BY COALESCE(ended_at, started_at) DESC, id DESC
            LIMIT 1
            """,
            lowered,
        ).fetchone()

    if {"name", "sequence", "closed_at", "standings_snapshot", "scorers_snapshot"}.issubset(cols):
        return conn.execute(
            f"""
            SELECT id, kind, name, sequence, closed_at, standings_snapshot, scorers_snapshot
            FROM competition_editions
            WHERE LOWER(status)='finished' AND LOWER(kind) IN ({placeholders})
            ORDER BY closed_at DESC, id DESC
            LIMIT 1
            """,
            lowered,
        ).fetchone()
    return None


def _edition_data(edition) -> tuple[str, str | None, list[dict], list[dict]]:
    keys = set(edition.keys()) if edition is not None else set()
    if "final_snapshot_json" in keys:
        snap = _snapshot(edition["final_snapshot_json"])
        return (
            str(edition["label"] or "Competencia"),
            str(edition["ended_at"] or "") or None,
            snap["standings"],
            snap["scorers"],
        )
    return (
        str(edition["name"] or "Competencia"),
        str(edition["closed_at"] or "") or None,
        _legacy_list(edition["standings_snapshot"]),
        _legacy_list(edition["scorers_snapshot"]),
    )


def _champion_payload(conn: sqlite3.Connection, edition) -> dict | None:
    if not edition:
        return None
    competition, closed_at, standings, _ = _edition_data(edition)
    if not standings:
        return None
    first = next((row for row in standings if int(row.get("position") or 0) == 1), standings[0])
    team = str(first.get("team") or "").strip()
    if not team:
        return None
    return {
        "competition_id": int(edition["id"]),
        "competition": competition,
        "kind": str(edition["kind"]),
        "team": team,
        "manager": _manager_at(conn, team, closed_at),
    }


def _scorer_payload(conn: sqlite3.Connection, edition) -> dict | None:
    if not edition:
        return None
    competition, closed_at, _, scorers = _edition_data(edition)
    if not scorers:
        return None
    first = max(scorers, key=lambda row: int(row.get("goals") or 0))
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
        "competition": competition,
        "player": player,
        "goals": goals,
        "team": team,
        "manager": _manager_at(conn, team, closed_at),
    }


def latest_honours_payload(conn: sqlite3.Connection) -> dict:
    latest_league = _latest_finished(conn, ("season", "preseason"))
    latest_cup = _latest_finished(conn, ("cup",))
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
