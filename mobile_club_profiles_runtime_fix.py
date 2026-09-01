"""Runtime-safe Discord username resolution for AJPA Mobile club profiles.

The mobile API can run in a Railway process where Discord's run_bot module is
intentionally never imported. Importing run_bot from an HTTP request can execute
the full Discord startup path and block that request until Railway returns 502.

This patch therefore never imports the gateway runtime. If it is already loaded
we read the cached member. Otherwise we use one cached Discord REST guild-member
request with the bot token. Public profiles never expose a raw Discord snowflake
as the visible DT name.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import mobile_club_profiles_api_patch as profiles

_DISCORD_API = "https://discord.com/api/v10"
_CACHE_TTL = 300.0
_cache_lock = threading.Lock()
_cached_at = 0.0
_cached_users: dict[int, str] = {}


def _guild_id() -> str:
    raw = (
        os.getenv("AJPA_MOBILE_GUILD_ID")
        or os.getenv("DISCORD_GUILD_ID")
        or ""
    ).strip()
    try:
        return str(int(raw)) if raw else ""
    except (TypeError, ValueError):
        return ""


def _clean_label(label: str | None, club: str) -> str | None:
    value = str(label or "").strip()
    if not value:
        return None
    suffix = f" | {club}"
    if value.casefold().endswith(suffix.casefold()):
        value = value[: -len(suffix)].rstrip()
    return value or None


def _runtime_username(user_id: int, club: str) -> str | None:
    # Critical: never `import run_bot` here. Only inspect it if another production
    # path has already loaded the module.
    run_bot = sys.modules.get("run_bot")
    if run_bot is None:
        return None
    try:
        runtime = getattr(run_bot, "runtime", None)
        bot = getattr(runtime, "bot", None)
        guild = bot.get_guild(int(_guild_id())) if bot and _guild_id() else None
        member = guild.get_member(int(user_id)) if guild else None
        if not member:
            return None
        # The product asks for the Discord username, not the numeric ID and not
        # the generated `Nombre | Equipo` server nickname.
        return _clean_label(getattr(member, "name", None), club)
    except Exception:
        return None


def _refresh_rest_cache() -> None:
    global _cached_at, _cached_users
    token = str(os.getenv("DISCORD_TOKEN") or "").strip()
    guild_id = _guild_id()
    if not token or not guild_id:
        return

    req = urllib.request.Request(
        f"{_DISCORD_API}/guilds/{guild_id}/members?limit=1000",
        method="GET",
        headers={
            "Authorization": f"Bot {token}",
            "Accept": "application/json",
            "User-Agent": "AJPA-Transfer-Market-Mobile/0.3",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        users: dict[int, str] = {}
        for member in payload if isinstance(payload, list) else []:
            user = member.get("user") or {}
            raw_id = str(user.get("id") or "")
            username = str(user.get("username") or "").strip()
            if raw_id.isdigit() and username:
                users[int(raw_id)] = username
        if users:
            _cached_users = users
            _cached_at = time.monotonic()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        # Username lookup is cosmetic. Never make a public profile fail if Discord
        # is temporarily unavailable or rate-limits this cache refresh.
        return


def _rest_username(user_id: int) -> str | None:
    global _cached_at
    now = time.monotonic()
    if now - _cached_at > _CACHE_TTL:
        with _cache_lock:
            if time.monotonic() - _cached_at > _CACHE_TTL:
                _refresh_rest_cache()
                # Avoid hammering Discord repeatedly when a refresh failed.
                if _cached_at == 0.0:
                    _cached_at = time.monotonic()
    return _cached_users.get(int(user_id))


def _safe_cached_discord_name(user_id: int | None, club: str) -> str | None:
    if not user_id:
        return None
    return _runtime_username(int(user_id), club) or _rest_username(int(user_id))


def _safe_manager_payload(conn, canonical: str) -> dict:
    row = profiles._owner_row(conn, canonical)
    if not row:
        return {"user_id": None, "name": "Sin DT asignado"}
    user_id = int(row["user_id"])
    name = _safe_cached_discord_name(user_id, canonical) or profiles._stored_discord_name(conn, user_id)
    return {
        "user_id": str(user_id),
        # Never expose the raw snowflake as visible profile text.
        "name": _clean_label(name, canonical) or "DT asignado",
    }


def apply_mobile_club_profiles_runtime_fix() -> None:
    profiles._cached_discord_name = _safe_cached_discord_name
    profiles._manager_payload = _safe_manager_payload
    print("AJPA Mobile: usernames Discord seguros en perfiles; requests nunca importan run_bot")
