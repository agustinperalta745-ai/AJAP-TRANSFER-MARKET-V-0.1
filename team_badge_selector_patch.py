"""Use Staff-uploaded club emojis safely in the team selector.

Configured clubs use their manual server emoji from the exact Discord guild that
opened the selector. AJAP does not create, version, delete, or reuse these emojis
across servers. Clubs without a configured/manual emoji keep the country flag.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import json_team_selection_patch as json_selector
import team_assignment as teams


APP = None
BOT = None

MANUAL_EMOJI_NAMES = {
    "Manchester City": "mancity",
    "Everton": "Everton",
    "Tottenham Hotspur": "TOT",
    "Villarreal": "villa",
    "Real Betis": "betis",
    "Aston Villa": "aston",
    "Fulham": "FUL",
    "Sevilla": "SEV",
    "Celta de Vigo": "vigo",
    "Paris Saint-Germain": "PSG",
    "Olympique de Lyon": "lyon",
}


def _current_guild():
    if BOT is None:
        return None
    try:
        guild_id = int(guild_isolation._CURRENT_GUILD_ID.get())
    except Exception:
        return None
    return BOT.get_guild(guild_id)


def _manual_badge_emoji(guild, club: str):
    """Resolve only from the supplied guild; never from a cross-guild cache."""
    if guild is None:
        return None
    manual_name = MANUAL_EMOJI_NAMES.get(str(club))
    if not manual_name:
        return None

    # Match case-insensitively so Staff uploads are less fragile.
    wanted = manual_name.casefold()
    emoji = next(
        (
            item
            for item in guild.emojis
            if str(getattr(item, "name", "")).casefold() == wanted
        ),
        None,
    )
    if emoji is None or not getattr(emoji, "available", True):
        return None
    return emoji


def _find_badge_emoji(guild, club: str):
    return _manual_badge_emoji(guild, club)


def _selector_emoji(club: str, country: str, guild=None):
    target_guild = guild or _current_guild()
    badge = _manual_badge_emoji(target_guild, club)
    if badge is not None:
        return badge
    return json_selector._country_emoji(country)


def _badge_welcome_embed(guild=None):
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

    target_guild = guild or _current_guild()
    for row in rows[:25]:
        club = row["name"]
        status = "🔒 Ya asignado" if club.casefold() in occupied else "✅ Disponible"
        icon = _selector_emoji(club, row["country"], target_guild)
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
        def __init__(self, guild=None):
            rows = json_selector._json_team_rows()[:25]
            occupied = {str(row["name"]).casefold() for row in teams.assignments()}
            target_guild = guild or _current_guild()
            options = [
                discord.SelectOption(
                    label=row["name"][:100],
                    description=(
                        f"{row['country']} • "
                        f"{'🔒 Ya asignado' if row['name'].casefold() in occupied else '✅ Disponible'}"
                    )[:100],
                    value=row["name"],
                    emoji=_selector_emoji(row["name"], row["country"], target_guild),
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
        def __init__(self, guild=None):
            super().__init__(timeout=300)
            if json_selector._json_team_rows():
                self.add_item(BadgeTeamSelect(guild=guild))

    teams.TeamSelect = BadgeTeamSelect
    teams.TeamChoiceView = BadgeTeamChoiceView
    teams.welcome_embed = _badge_welcome_embed


async def _ensure_guild_badges(guild):
    # Manual-only policy: just verify configured emojis; never create/delete them.
    for club, expected_name in MANUAL_EMOJI_NAMES.items():
        emoji = _manual_badge_emoji(guild, club)
        if emoji is not None:
            print(
                f"AJAP escudo manual OK: guild={guild.id} club={club} "
                f"emoji=:{emoji.name}: id={emoji.id}"
            )
        else:
            print(
                f"WARNING AJAP escudo manual: guild={guild.id} club={club} "
                f"no tiene :{expected_name}:; se usa bandera"
            )
    return 0


async def _check_manual_badges_on_ready():
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
    bot.add_listener(_check_manual_badges_on_ready, "on_ready")
    runtime._ajap_team_badge_selector_patch = True
    print("AJAP selector escudos manual-only activo: City=:mancity: + Everton=:Everton: + Tottenham=:TOT: + Villarreal=:villa: + Real Betis=:betis: + Aston Villa=:aston: + Fulham=:FUL: + Sevilla=:SEV: + Celta de Vigo=:vigo: + PSG=:PSG: + Lyon=:lyon:")


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
