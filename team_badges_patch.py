"""Escudos oficiales de clubes para los embeds de AJAP.

Los PNG viven en assets/teams cuando existe un fallback público. Para el resto,
`badge_reliability_patch` usa el emoji manual del servidor como thumbnail. Esta
capa detecta el club en cualquier embed para que TODOS los equipos configurados
puedan mostrar el escudo grande, no solo los primeros clubes que tenían PNG.
"""

from __future__ import annotations

import re
import discord

RAW_BASE = "https://raw.githubusercontent.com/agustinperalta745-ai/AJAP-TRANSFER-MARKET-V-0.1/main/assets/teams"

TEAM_BADGES = {
    # Query versioned on purpose: Discord aggressively caches failed/old thumbnail
    # fetches. Bumping this forces a fresh request without changing the asset path.
    "Manchester City": f"{RAW_BASE}/manchester_city.png?v=8",
    "Tottenham Hotspur": f"{RAW_BASE}/tottenham_hotspur.png",
    "Fulham": f"{RAW_BASE}/fulham.png",
    "Everton": f"{RAW_BASE}/everton.png",
    "Aston Villa": f"{RAW_BASE}/aston_villa.png",
    "Real Betis": f"{RAW_BASE}/real_betis.png",
    "Sevilla": f"{RAW_BASE}/sevilla.png",
    "Villarreal": f"{RAW_BASE}/villarreal.png",
}

# IMPORTANTE: esta lista ya no representa solamente clubes con PNG en GitHub.
# También es el catálogo de detección usado por badge_reliability_patch para
# convertir el emoji manual de Discord en el escudo grande del embed.
ALIASES = {
    "manchester city": "Manchester City",
    "man city": "Manchester City",
    "city": "Manchester City",
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
    "west ham united": "West Ham United",
    "west ham": "West Ham United",
    "newcastle united": "Newcastle United",
    "newcastle": "Newcastle United",
    "middlesbrough": "Middlesbrough",
    "bolton wanderers": "Bolton Wanderers",
    "bolton": "Bolton Wanderers",
    "ajax": "Ajax",
    "torino": "Torino",
    "fiorentina": "Fiorentina",
    "lazio": "Lazio",
    "porto": "Porto",
    "fc porto": "Porto",
    "benfica": "Benfica",
    "sl benfica": "Benfica",
    "real zaragoza": "Real Zaragoza",
    "zaragoza": "Real Zaragoza",
    "celta de vigo": "Celta de Vigo",
    "celta vigo": "Celta de Vigo",
    "celta": "Celta de Vigo",
    "paris saint-germain": "Paris Saint-Germain",
    "paris saint germain": "Paris Saint-Germain",
    "psg": "Paris Saint-Germain",
    "olympique de lyon": "Olympique de Lyon",
    "olympique lyon": "Olympique de Lyon",
    "lyon": "Olympique de Lyon",
    "olympique de marsella": "Olympique de Marsella",
    "olympique marsella": "Olympique de Marsella",
    "marsella": "Olympique de Marsella",
    "marseille": "Olympique de Marsella",
    "atletico de madrid": "Atletico de Madrid",
    "atlético de madrid": "Atletico de Madrid",
    "atletico madrid": "Atletico de Madrid",
    "atlético madrid": "Atletico de Madrid",
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
    # mencione rivales, ofertas o destinos. Con ALIASES completo esto cubre todos
    # los clubes que tienen emoji manual en AJAP.
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
    print("AJAP escudos activos: club detectado => thumbnail oficial/manual")


apply_team_badges_patch()
