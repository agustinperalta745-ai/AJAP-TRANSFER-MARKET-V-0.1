"""AJAP badge reliability layer.

Fixes two independent Discord rendering problems:
- Team selector badges are custom guild emojis. Old/broken Manchester City emoji
  revisions are removed once per process and a fresh revision is provisioned.
- Embed thumbnails use the already-provisioned Discord emoji CDN URL instead of a
  raw GitHub URL. If no usable club emoji exists, the automatic badge thumbnail is
  removed so Discord never renders the broken-image placeholder.

This module is intentionally imported after team_badge_selector_patch and before
run_bot starts the client.
"""

from __future__ import annotations

import discord

import team_badges_patch as badges
import team_badge_selector_patch as selector


CITY = "Manchester City"
CITY_EMOJI_VERSION = 6
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

    # Purge every previous revision, including a stale current-name object if one
    # already exists from a failed deploy. It will be recreated from the current
    # PNG immediately below by the normal provisioner.
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
                "WARNING AJAP badge refresh: falta permiso para borrar emojis "
                f"en guild={guild_id}; se intentará reutilizar/crear {current_name}"
            )
            break
        except discord.HTTPException as exc:
            print(
                "WARNING AJAP badge refresh: no se pudo borrar "
                f"{emoji.name} en guild={guild_id}: {exc}"
            )

    # Clear any in-process cached objects whose IDs may now be invalid.
    for key in list(selector._EMOJI_CACHE):
        if key[0] == guild_id and str(key[1]).startswith(base):
            selector._EMOJI_CACHE.pop(key, None)

    _REFRESHED_GUILDS.add(guild_id)


async def _reliable_ensure_guild_badges(guild: discord.Guild):
    await _delete_old_city_emojis_once(guild)
    return await _original_ensure_guild_badges(guild)


selector._ensure_guild_badges = _reliable_ensure_guild_badges

# The original team_badges_patch already wrapped Embed.to_dict. Wrap the resulting
# serializer once more: replace its raw GitHub thumbnail with the Discord CDN URL
# of the guild emoji. This survives message edits and avoids Discord's broken-image
# placeholder. If the emoji is unavailable, omit the automatic thumbnail entirely.
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

        # Only remove thumbnails automatically injected by team_badges_patch.
        thumb = data.get("thumbnail") or {}
        url = str(thumb.get("url") or "")
        if url.startswith(badges.RAW_BASE):
            data.pop("thumbnail", None)
        return data

    discord.Embed.to_dict = _reliable_to_dict
    discord.Embed._ajap_badge_reliability_patch = True
    print(
        "AJAP badge reliability activo: selector refrescado + embeds desde Discord CDN"
    )
