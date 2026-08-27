"""AJAP badge reliability layer.

Fixes two independent Discord rendering problems:
- Team selector badges are custom guild emojis. Old/broken Manchester City emoji
  revisions are removed once per process and a fresh revision is provisioned.
- Embed thumbnails prefer the already-provisioned Discord emoji CDN URL. If no
  usable club emoji exists, keep the direct cache-busted PNG URL as fallback.

This module is intentionally imported after team_badge_selector_patch and before
run_bot starts the client.
"""

from __future__ import annotations

import discord

import team_badges_patch as badges
import team_badge_selector_patch as selector


CITY = "Manchester City"
CITY_EMOJI_VERSION = 8
_REFRESHED_GUILDS: set[int] = set()

# Force a genuinely new Discord emoji ID/name after the failed cached revisions.
selector.SELECTOR_EMOJI_VERSIONS[CITY] = CITY_EMOJI_VERSION

_original_ensure_guild_badges = selector._ensure_guild_badges


async def _delete_old_city_emojis_once(guild: discord.Guild) -> None:
    guild_id = int(guild.id)
    if guild_id in _REFRESHED_GUILDS:
        return

    base = "ajap_manchester_city"
    current_name = selector._emoji_name(CITY)

    stale = [
        emoji
        for emoji in list(guild.emojis)
        if emoji.name == base or emoji.name.startswith(base + "_v")
    ]

    for emoji in stale:
        try:
            await emoji.delete(reason="AJAP: refresh Manchester City badge asset")
        except discord.Forbidden:
            print(
                "WARNING AJAP badge refresh: falta permiso Gestionar expresiones/emojis "
                f"en guild={guild_id}; se conserva fallback PNG y se intentará {current_name}"
            )
            break
        except discord.HTTPException as exc:
            print(
                "WARNING AJAP badge refresh: no se pudo borrar "
                f"{emoji.name} en guild={guild_id}: {exc}"
            )

    for key in list(selector._EMOJI_CACHE):
        if key[0] == guild_id and str(key[1]).startswith(base):
            selector._EMOJI_CACHE.pop(key, None)

    _REFRESHED_GUILDS.add(guild_id)


async def _reliable_ensure_guild_badges(guild: discord.Guild):
    await _delete_old_city_emojis_once(guild)
    result = await _original_ensure_guild_badges(guild)
    emoji = selector._find_badge_emoji(guild, CITY)
    if emoji is not None:
        print(
            f"AJAP Manchester City badge OK: guild={guild.id} "
            f"emoji={emoji.name} id={emoji.id}"
        )
    else:
        print(
            f"WARNING AJAP Manchester City badge: guild={guild.id} sin emoji; "
            "los embeds usarán PNG directo y el selector usará bandera hasta otorgar "
            "Gestionar expresiones/emojis al bot"
        )
    return result


selector._ensure_guild_badges = _reliable_ensure_guild_badges

# Prefer the Discord CDN custom emoji whenever it exists. Crucially, do NOT delete
# the raw PNG thumbnail when the emoji is unavailable: that behaviour was leaving
# Manchester City completely blank. The direct URL is now a real fallback.
if not getattr(discord.Embed, "_ajap_badge_reliability_patch", False):
    _previous_to_dict = discord.Embed.to_dict

    def _reliable_to_dict(self):
        data = _previous_to_dict(self)
        club = badges._detect_club(data)
        if not club:
            return data

        guild = selector._current_guild()
        emoji = selector._find_badge_emoji(guild, club) if guild is not None else None
        if emoji is not None and getattr(emoji, "available", True):
            data["thumbnail"] = {"url": str(emoji.url)}
            return data

        # Guaranteed second path: keep/inject the public PNG instead of removing it.
        fallback = badges.TEAM_BADGES.get(club)
        if fallback:
            data["thumbnail"] = {"url": fallback}
        return data

    discord.Embed.to_dict = _reliable_to_dict
    discord.Embed._ajap_badge_reliability_patch = True
    print(
        "AJAP badge reliability activo: Discord CDN preferido + PNG directo de fallback"
    )
