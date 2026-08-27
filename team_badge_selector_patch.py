"""Show club badges in the initial team selector using guild custom emojis.

Discord select menus do not accept arbitrary image URLs. To display the real club
crest beside each option we provision a small custom emoji in every guild from the
PNG already stored in assets/teams, then reuse that emoji in the JSON-only selector.
If the bot lacks emoji-management permission, the selector safely falls back to the
country flag instead of breaking.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import discord

import guild_isolation_patch as guild_isolation
import json_team_selection_patch as json_selector
import team_assignment as teams
import team_badges_patch as badges


APP = None
BOT = None
ASSET_DIR = Path(__file__).resolve().parent / "assets" / "teams"
_EMOJI_CACHE = {}
_WARNED_GUILDS = set()


def _emoji_name(club: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(club or ""))
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_name).strip("_").lower()
    name = f"ajap_{slug}" if slug else "ajap_club"
    return name[:32].rstrip("_")


def _asset_path(club: str):
    url = badges.TEAM_BADGES.get(club)
    if not url:
        return None
    filename = str(url).rsplit("/", 1)[-1]
    path = ASSET_DIR / filename
    return path if path.is_file() else None


def _current_guild():
    if BOT is None:
        return None
    try:
        guild_id = int(guild_isolation._CURRENT_GUILD_ID.get())
    except Exception:
        return None
    return BOT.get_guild(guild_id)


def _find_badge_emoji(guild, club: str):
    if guild is None:
        return None
    name = _emoji_name(club)
    cached = _EMOJI_CACHE.get((int(guild.id), name))
    if cached is not None:
        return cached
    emoji = discord.utils.get(guild.emojis, name=name)
    if emoji is not None:
        _EMOJI_CACHE[(int(guild.id), name)] = emoji
    return emoji


def _selector_emoji(club: str, country: str):
    guild = _current_guild()
    badge = _find_badge_emoji(guild, club)
    return badge if badge is not None else json_selector._country_emoji(country)


def _badge_welcome_embed():
    rows = json_selector._json_team_rows()
    occupied = {str(row["name"]).casefold() for row in teams.assignments()}
    embed = discord.Embed(
        title="⚽ Elegí tu equipo",
        description=(
            "Seleccioná el club que vas a manejar en **AJAP Transfer Market**.\n\n"
            "Solo aparecen equipos con plantilla cargada desde JSON."
        ),
    )

    if not rows:
        embed.description = "Todavía no hay equipos con JSON cargado disponibles."
        return embed

    for row in rows[:25]:
        club = row["name"]
        status = "🔒 Ya asignado" if club.casefold() in occupied else "✅ Disponible"
        icon = _selector_emoji(club, row["country"])
        embed.add_field(
            name=f"{icon} {club}",
            value=f"{row['country']} • {status}",
            inline=False,
        )

    embed.set_footer(text=f"{len(rows)} equipo(s) con JSON • 1 equipo por cuenta")
    return embed


def _install_badge_selector():
    BaseTeamSelect = teams.TeamSelect

    class BadgeTeamSelect(BaseTeamSelect):
        def __init__(self):
            rows = json_selector._json_team_rows()[:25]
            occupied = {str(row["name"]).casefold() for row in teams.assignments()}
            options = [
                discord.SelectOption(
                    label=row["name"][:100],
                    description=(
                        f"{row['country']} • "
                        f"{'🔒 Ya asignado' if row['name'].casefold() in occupied else '✅ Disponible'}"
                    )[:100],
                    value=row["name"],
                    emoji=_selector_emoji(row["name"], row["country"]),
                )
                for row in rows
            ]
            discord.ui.Select.__init__(
                self,
                placeholder="Elegí tu equipo",
                min_values=1,
                max_values=1,
                options=options,
            )

    class BadgeTeamChoiceView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=300)
            if json_selector._json_team_rows():
                self.add_item(BadgeTeamSelect())

    teams.TeamSelect = BadgeTeamSelect
    teams.TeamChoiceView = BadgeTeamChoiceView
    teams.welcome_embed = _badge_welcome_embed


async def _ensure_guild_badges(guild):
    created = 0
    for club in badges.TEAM_BADGES:
        path = _asset_path(club)
        if path is None:
            continue

        name = _emoji_name(club)
        existing = discord.utils.get(guild.emojis, name=name)
        if existing is not None:
            _EMOJI_CACHE[(int(guild.id), name)] = existing
            continue

        try:
            emoji = await guild.create_custom_emoji(
                name=name,
                image=path.read_bytes(),
                reason=f"AJAP: escudo de {club} para selector de equipos",
            )
        except discord.Forbidden:
            if guild.id not in _WARNED_GUILDS:
                _WARNED_GUILDS.add(guild.id)
                print(
                    "WARNING AJAP escudos selector: el bot necesita permiso "
                    f"Gestionar expresiones/emojis en guild={guild.id}; se usan banderas como fallback"
                )
            break
        except discord.HTTPException as exc:
            print(f"WARNING AJAP escudos selector: no se pudo crear {name} en guild={guild.id}: {exc}")
            continue

        _EMOJI_CACHE[(int(guild.id), name)] = emoji
        created += 1

    if created:
        print(f"AJAP escudos selector: {created} emoji(s) de club creados en guild={guild.id}")


async def _provision_badges_on_ready():
    if BOT is None:
        return
    for guild in BOT.guilds:
        await _ensure_guild_badges(guild)


def apply_team_badge_selector_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_team_badge_selector_patch", False):
        return

    _install_badge_selector()
    bot.add_listener(_provision_badges_on_ready, "on_ready")
    runtime._ajap_team_badge_selector_patch = True
    print("AJAP selector con escudos activo: PNG -> emoji de club; bandera como fallback")


_original_apply_json_team_selection_patch = json_selector.apply_json_team_selection_patch


def _apply_json_then_badges(runtime, bot):
    _original_apply_json_team_selection_patch(runtime, bot)
    apply_team_badge_selector_patch(runtime, bot)


if not getattr(
    json_selector.apply_json_team_selection_patch,
    "_ajap_team_badge_selector_wrapped",
    False,
):
    _apply_json_then_badges._ajap_team_badge_selector_wrapped = True
    json_selector.apply_json_team_selection_patch = _apply_json_then_badges
