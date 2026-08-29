"""Final badge reliability layer for AJAP.

Every configured club prefers the Staff-uploaded emoji from the exact Discord
guild as its embed thumbnail. Public PNGs remain only as fallbacks for clubs that
already have one in assets/teams.
"""

from __future__ import annotations

import discord

import team_badges_patch as badges
import team_badge_selector_patch as selector

# Accept both historical/canonical variants so the same manual emoji keeps
# working even if a JSON/seed names the club slightly differently.
selector.MANUAL_EMOJI_NAMES.setdefault("Zaragoza", "zara")
selector.MANUAL_EMOJI_NAMES.setdefault("Real Zaragoza", "zara")
selector.MANUAL_EMOJI_NAMES.setdefault("Atletico Madrid", "atletico")
selector.MANUAL_EMOJI_NAMES.setdefault("Atletico de Madrid", "atletico")
selector.MANUAL_EMOJI_NAMES.setdefault("Sevilla", "SEV")
selector.MANUAL_EMOJI_NAMES.setdefault("Sevilla FC", "SEV")
selector.MANUAL_EMOJI_NAMES.setdefault("Villarreal", "villa")
selector.MANUAL_EMOJI_NAMES.setdefault("Villarreal CF", "villa")


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
    print("AJAP badge reliability activo: todos los clubes usan emoji manual + PNG fallback")

# Final Staff bridge: when Perfil Usuario builds the team list, pass the concrete
# interaction.guild into both the embed and select so manual emojis can never come
# from another server/context.
import manual_city_exact_guild_patch  # noqa: F401,E402

# Activate the Discord identity projection too. This patch was already implemented
# but was never imported by the production startup chain, so club roles (and their
# shield icons when the guild supports ROLE_ICONS) were not being created/assigned.
# Importing it here is intentionally late: badge aliases are final and run_bot will
# later call the wrapped guild-isolation installer with the definitive team logic.
import team_role_identity_patch  # noqa: F401,E402

# Cola Staff para pasar resultados oficiales a GES Liga. Se importa después de la
# capa de escudos para que la placa use los emojis definitivos de cada club.
import league_ges_result_queue_patch  # noqa: F401,E402
