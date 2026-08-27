"""Final badge reliability layer for AJAP.

Manchester City now relies on the Staff-uploaded :mancity: emoji from the exact
Discord guild. No automatic guild emoji creation and no application-owned emoji
are used anymore. Embed thumbnails prefer that same manual emoji CDN URL and fall
back to the public PNG only when the manual emoji is unavailable.
"""

from __future__ import annotations

import discord

import team_badges_patch as badges
import team_badge_selector_patch as selector


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

        fallback = badges.TEAM_BADGES.get(club)
        if fallback:
            data["thumbnail"] = {"url": fallback}
        return data

    discord.Embed.to_dict = _reliable_to_dict
    discord.Embed._ajap_badge_reliability_patch = True
    print("AJAP badge reliability activo: emoji manual exacto + PNG fallback")

# Final Staff bridge: when Perfil Usuario builds the team list, pass the concrete
# interaction.guild into both the embed and select so :mancity: can never come
# from another server/context.
import manual_city_exact_guild_patch  # noqa: F401,E402
