"""Runtime safety fix for AJPA Mobile club profiles.

The mobile API can run in a Railway process where Discord's run_bot module is
intentionally never imported. Importing run_bot from an HTTP request can execute
the full Discord startup path and block that request until Railway returns 502.

Only inspect an already-loaded Discord runtime; never import it from an API
request. Stored nickname state remains the safe fallback used by the profile API.
"""

from __future__ import annotations

import os
import sys

import mobile_club_profiles_api_patch as profiles


def _safe_cached_discord_name(user_id: int | None, club: str) -> str | None:
    if not user_id:
        return None

    # Critical: never `import run_bot` here. On the mobile/API Railway worker that
    # import can start the Discord gateway and block the HTTP handler, surfacing as
    # a 502 in the APK. Only use the module when production already loaded it.
    run_bot = sys.modules.get("run_bot")
    if run_bot is None:
        return None

    try:
        runtime = getattr(run_bot, "runtime", None)
        bot = getattr(runtime, "bot", None)
        raw_guild = (
            os.getenv("AJPA_MOBILE_GUILD_ID")
            or os.getenv("DISCORD_GUILD_ID")
            or ""
        ).strip()
        guild = bot.get_guild(int(raw_guild)) if bot and raw_guild else None
        member = guild.get_member(int(user_id)) if guild else None
        if not member:
            return None

        label = str(member.display_name or member.name or "").strip()
        suffix = f" | {club}"
        if label.casefold().endswith(suffix.casefold()):
            label = label[: -len(suffix)].rstrip()
        return label or None
    except Exception:
        return None


def apply_mobile_club_profiles_runtime_fix() -> None:
    profiles._cached_discord_name = _safe_cached_discord_name
    print("AJPA Mobile club profiles runtime fix activo: requests nunca importan run_bot")
