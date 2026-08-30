"""Discord OAuth validation for the AJPA mobile read-only API.

The mobile app authenticates directly with Discord using Authorization Code +
PKCE. This backend receives the resulting Bearer token, validates that Discord
issued it for the AJPA application, resolves guild membership/admin permission,
and maps the Discord user to the same club authority already used by the bot.

No OAuth token is persisted here and no database writes are performed.
"""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from http import HTTPStatus

DISCORD_API = "https://discord.com/api/v10"
ADMINISTRATOR_PERMISSION = 1 << 3
ACTIVE_HISTORY_ACTIONS = {"ASIGNADO", "ASIGNADO_VACANTE_ADMIN"}
INACTIVE_HISTORY_ACTIONS = {"DESVINCULADO_ADMIN", "RENUNCIA_DT"}


class OAuthError(Exception):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.UNAUTHORIZED):
        super().__init__(message)
        self.message = message
        self.status = status


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _club_deleted(conn: sqlite3.Connection, club: str | None) -> bool:
    if not club or not _table_exists(conn, "deleted_teams"):
        return False
    return bool(
        conn.execute(
            "SELECT 1 FROM deleted_teams WHERE name=? COLLATE NOCASE LIMIT 1",
            (club,),
        ).fetchone()
    )


def resolve_club_readonly(conn: sqlite3.Connection, user_id: int) -> str | None:
    """Mirror AJPA's assignment authority without healing/mutating the DB."""
    observed = None
    if _table_exists(conn, "clubs"):
        row = conn.execute(
            "SELECT name FROM clubs WHERE user_id=? LIMIT 1", (int(user_id),)
        ).fetchone()
        if row:
            observed = str(row["name"] or "").strip() or None
            if _club_deleted(conn, observed):
                observed = None

    history = None
    if _table_exists(conn, "club_assignment_history"):
        history = conn.execute(
            """
            SELECT club, action
            FROM club_assignment_history
            WHERE user_id=?
            ORDER BY id DESC LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()

    if history:
        action = str(history["action"] or "").strip().upper()
        history_club = str(history["club"] or "").strip() or None
        if action in INACTIVE_HISTORY_ACTIONS:
            return None
        if action in ACTIVE_HISTORY_ACTIONS:
            if observed:
                return observed
            if history_club and not _club_deleted(conn, history_club):
                return history_club
            return None

    if _table_exists(conn, "club_assignment_guard"):
        guard = conn.execute(
            "SELECT club, active FROM club_assignment_guard WHERE user_id=? LIMIT 1",
            (int(user_id),),
        ).fetchone()
        if guard:
            protected = str(guard["club"] or "").strip() or None
            if not bool(guard["active"]):
                return None
            if protected and not _club_deleted(conn, protected):
                return protected

    return observed


def _discord_get(path: str, token: str):
    request = urllib.request.Request(
        f"{DISCORD_API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "AJPA-Transfer-Market-Mobile/0.2",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise OAuthError("La sesión de Discord no es válida o venció.") from exc
        raise OAuthError(
            "Discord no pudo validar la sesión en este momento.",
            HTTPStatus.BAD_GATEWAY,
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OAuthError(
            "No se pudo contactar a Discord para validar la sesión.",
            HTTPStatus.BAD_GATEWAY,
        ) from exc


def _bearer_token(authorization: str | None) -> str:
    raw = (authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        raise OAuthError("Falta iniciar sesión con Discord.")
    token = raw[7:].strip()
    if not token:
        raise OAuthError("Falta iniciar sesión con Discord.")
    return token


def discord_identity(authorization: str | None) -> dict:
    token = _bearer_token(authorization)
    auth = _discord_get("/oauth2/@me", token)

    expected_client_id = (os.getenv("DISCORD_CLIENT_ID") or "").strip()
    application_id = str((auth.get("application") or {}).get("id") or "").strip()
    if expected_client_id and application_id != expected_client_id:
        raise OAuthError("El login no pertenece a la aplicación AJPA.")

    scopes = {str(scope) for scope in auth.get("scopes") or []}
    if "identify" not in scopes:
        raise OAuthError("Discord no concedió el permiso identify.", HTTPStatus.FORBIDDEN)
    if "guilds" not in scopes:
        raise OAuthError("Discord no concedió el permiso guilds.", HTTPStatus.FORBIDDEN)

    user = auth.get("user") or {}
    user_id = str(user.get("id") or "").strip()
    if not user_id.isdigit():
        raise OAuthError("Discord no devolvió un usuario válido.")

    raw_guild_id = (
        os.getenv("AJPA_MOBILE_GUILD_ID")
        or os.getenv("DISCORD_GUILD_ID")
        or ""
    ).strip()
    guild_id = str(int(raw_guild_id)) if raw_guild_id else ""

    guilds = _discord_get("/users/@me/guilds", token)
    guild = next(
        (item for item in guilds if str(item.get("id") or "") == guild_id),
        None,
    )

    permissions = int(str((guild or {}).get("permissions") or "0"))
    is_owner = bool((guild or {}).get("owner"))
    return {
        "user": {
            "id": user_id,
            "username": str(user.get("username") or ""),
            "global_name": user.get("global_name"),
            "avatar": user.get("avatar"),
        },
        "guild": {
            "id": guild_id or None,
            "in_guild": guild is not None,
            "is_staff": bool(guild and (is_owner or permissions & ADMINISTRATOR_PERMISSION)),
        },
    }


def profile_payload(conn: sqlite3.Connection, identity: dict) -> dict:
    user = identity["user"]
    guild = identity["guild"]
    user_id = int(user["id"])
    club = resolve_club_readonly(conn, user_id) if guild["in_guild"] else None

    balance = None
    roster_count = 0
    if club and _table_exists(conn, "club_finances"):
        row = conn.execute(
            "SELECT balance FROM club_finances WHERE club=? COLLATE NOCASE LIMIT 1",
            (club,),
        ).fetchone()
        balance = int(row["balance"]) if row else 0
    if club and _table_exists(conn, "roster_players"):
        roster_count = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM roster_players WHERE club=? COLLATE NOCASE",
                (club,),
            ).fetchone()["c"]
        )

    return {
        "authenticated": True,
        "read_only": True,
        "user": user,
        "in_guild": bool(guild["in_guild"]),
        "is_staff": bool(guild["is_staff"]),
        "club": club,
        "balance": balance,
        "roster_count": roster_count,
    }


def me_payload(conn: sqlite3.Connection, authorization: str | None) -> dict:
    return profile_payload(conn, discord_identity(authorization))
