"""Agrega los emojis de los clubes al FINAL DEL CLÁSICO de Radio Pasillo.

No cambia el texto, la chicana ni las menciones: el anuncio de resultado sigue
sin etiquetar a los DT. El primer equipo lleva su emoji adelante y el segundo
lo lleva al final, igual que el formato del anuncio de clásico confirmado.
"""

from __future__ import annotations

from contextvars import ContextVar

import discord

import classic_result_radio_patch as radio


_GUILD = ContextVar("ajap_classic_result_badge_guild", default=None)
_BASE_EMBED_FOR = radio._embed_for
_BASE_TEXT_FOR = radio._text_for
_BASE_PUBLISH_FOR_SOURCE = radio.publish_for_source


def _club_emoji(guild, club: str) -> str:
    if guild is None:
        return "⚽"
    try:
        import team_badge_selector_patch as selector
        import team_badges_patch as badges

        raw = str(club or "").strip()
        candidates = [raw]
        canonical = badges.ALIASES.get(raw.casefold())
        if canonical and canonical.casefold() != raw.casefold():
            candidates.append(canonical)

        for candidate in candidates:
            emoji = selector._find_badge_emoji(guild, candidate)
            if emoji is not None:
                return str(emoji)
    except Exception:
        pass
    return "⚽"


def _score_lines(match, guild):
    home_raw = str(match["home_team"])
    away_raw = str(match["away_team"])
    home = discord.utils.escape_markdown(home_raw)
    away = discord.utils.escape_markdown(away_raw)
    hg = int(match["home_goals"])
    ag = int(match["away_goals"])
    home_emoji = _club_emoji(guild, home_raw)
    away_emoji = _club_emoji(guild, away_raw)

    old = f"⚔️ **{home} {hg}–{ag} {away}**"
    new = f"⚔️ **{home_emoji} {home} {hg}–{ag} {away} {away_emoji}**"
    return old, new


def _embed_for_with_badges(match) -> discord.Embed:
    embed = _BASE_EMBED_FOR(match)
    old, new = _score_lines(match, _GUILD.get())
    if embed.description:
        embed.description = str(embed.description).replace(old, new, 1)
    return embed


def _text_for_with_badges(match) -> str:
    text = _BASE_TEXT_FOR(match)
    old, new = _score_lines(match, _GUILD.get())
    return str(text).replace(old, new, 1)


async def _publish_for_source_with_badges(runtime, bot, guild, source_message_id: int) -> bool:
    token = _GUILD.set(guild)
    try:
        return await _BASE_PUBLISH_FOR_SOURCE(runtime, bot, guild, source_message_id)
    finally:
        _GUILD.reset(token)


radio._embed_for = _embed_for_with_badges
radio._text_for = _text_for_with_badges
radio.publish_for_source = _publish_for_source_with_badges

print("AJAP Radio Pasillo: emojis de clubes activos en FINAL DEL CLÁSICO")
