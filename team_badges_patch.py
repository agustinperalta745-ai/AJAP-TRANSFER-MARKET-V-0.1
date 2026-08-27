"""Escudos oficiales de clubes para los embeds de AJAP.

Los PNG viven en assets/teams y se sirven desde el propio repositorio público.
Decoramos los embeds en el último momento (Embed.to_dict), así cualquier pantalla
que identifique claramente a un único club recibe su escudo sin duplicar lógica.
"""

from __future__ import annotations

import re
import discord

RAW_BASE = "https://raw.githubusercontent.com/agustinperalta745-ai/AJAP-TRANSFER-MARKET-V-0.1/main/assets/teams"

TEAM_BADGES = {
    "Manchester City": f"{RAW_BASE}/manchester_city.png",
    "Tottenham Hotspur": f"{RAW_BASE}/tottenham_hotspur.png",
    "Fulham": f"{RAW_BASE}/fulham.png",
    "Everton": f"{RAW_BASE}/everton.png",
    "Aston Villa": f"{RAW_BASE}/aston_villa.png",
    "Real Betis": f"{RAW_BASE}/real_betis.png",
    "Sevilla": f"{RAW_BASE}/sevilla.png",
    "Villarreal": f"{RAW_BASE}/villarreal.png",
}

ALIASES = {
    "manchester city": "Manchester City",
    "man city": "Manchester City",
    "tottenham hotspur": "Tottenham Hotspur",
    "tottenham": "Tottenham Hotspur",
    "spurs": "Tottenham Hotspur",
    "fulham": "Fulham",
    "everton": "Everton",
    "aston villa": "Aston Villa",
    "real betis": "Real Betis",
    "betis": "Real Betis",
    "sevilla": "Sevilla",
    "sevilla fc": "Sevilla",
    "villarreal": "Villarreal",
    "villarreal cf": "Villarreal",
}


def badge_url(club):
    if not club:
        return None
    key = str(club).strip().casefold()
    canonical = ALIASES.get(key)
    return TEAM_BADGES.get(canonical) if canonical else None


def _embed_text(data):
    parts = [str(data.get("title") or ""), str(data.get("description") or "")]
    author = data.get("author") or {}
    footer = data.get("footer") or {}
    parts.extend([str(author.get("name") or ""), str(footer.get("text") or "")])
    for field in data.get("fields") or []:
        parts.extend([str(field.get("name") or ""), str(field.get("value") or "")])
    return "\n".join(parts)


def _detect_club(data):
    # El título manda: suele indicar el club dueño de la pantalla aunque el cuerpo
    # mencione rivales, ofertas o destinos.
    title = str(data.get("title") or "").casefold()
    title_hits = []
    for alias, canonical in ALIASES.items():
        if re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", title):
            title_hits.append(canonical)
    title_hits = list(dict.fromkeys(title_hits))
    if len(title_hits) == 1:
        return title_hits[0]

    text = _embed_text(data).casefold()
    hits = []
    for alias, canonical in ALIASES.items():
        if re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", text):
            hits.append(canonical)
    hits = list(dict.fromkeys(hits))
    return hits[0] if len(hits) == 1 else None


def apply_team_badges_patch():
    if getattr(discord.Embed, "_ajap_team_badges_patch", False):
        return

    original_to_dict = discord.Embed.to_dict

    def to_dict(self):
        data = original_to_dict(self)
        # No pisamos imágenes/miniaturas que una pantalla haya elegido a propósito.
        if data.get("thumbnail") or data.get("image"):
            return data
        club = _detect_club(data)
        url = TEAM_BADGES.get(club) if club else None
        if url:
            data["thumbnail"] = {"url": url}
        return data

    discord.Embed.to_dict = to_dict
    discord.Embed._ajap_team_badges_patch = True
    print("AJAP escudos activos: club detectado => thumbnail oficial")


apply_team_badges_patch()
