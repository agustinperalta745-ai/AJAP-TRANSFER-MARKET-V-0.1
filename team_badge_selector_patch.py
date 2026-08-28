"""Use Staff-uploaded club emojis safely across AJAP team UI.

Configured clubs use their manual server emoji from the exact Discord guild that
opened the selector or generated the vacancy card. AJAP does not create,
version, delete, or reuse these emojis across servers. Clubs without a
configured/manual emoji keep the country flag in selectors and the normal title
in vacancy announcements.
"""

from __future__ import annotations

from contextvars import ContextVar

import discord

import guild_isolation_patch as guild_isolation
import json_team_selection_patch as json_selector
import team_assignment as teams


APP = None
BOT = None
_VACANCY_GUILD = ContextVar("ajap_vacancy_badge_guild", default=None)

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
    "Olympique de Marsella": "marcella",
    "Atletico de Madrid": "atletico",
    "Middlesbrough": "middle",
    "Bolton Wanderers": "bolton",
    "Ajax": "ajax",
    "Torino": "tor",
    "West Ham United": "weh",
    "Newcastle United": "newc",
    "Fiorentina": "fiore",
    "Lazio": "lazio",
    "Porto": "porto",
    "Benfica": "ben",
    "Zaragoza": "zara",
    "Galatasaray": "galata",
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


def _decorate_panel_with_badge(base):
    """Decorate one cached manager-panel function without changing its routing logic."""
    if not callable(base) or getattr(base, "_ajap_club_badge_title", False):
        return base

    def panel_with_badge(user_id: int, *args, **kwargs):
        embed = base(user_id, *args, **kwargs)
        runtime = APP
        if runtime is None or embed is None:
            return embed

        try:
            club = runtime.club_de(user_id)
        except Exception:
            club = None
        if not club:
            return embed

        badge = _manual_badge_emoji(_current_guild(), club)
        if badge is not None:
            # Mismo escudo en dos tamaños: emoji junto al nombre + thumbnail
            # grande a la derecha, exactamente como ya se veía en Aston Villa.
            embed.title = f"{badge} {str(club).upper()}"
            try:
                embed.set_thumbnail(url=str(badge.url))
            except Exception as exc:
                print(
                    "WARNING AJAP escudo grande panel: "
                    f"club={club} error={type(exc).__name__}: {exc}"
                )
        return embed

    panel_with_badge._ajap_club_badge_title = True
    panel_with_badge._ajap_club_badge_base = base
    return panel_with_badge


def _install_manager_panel_badge():
    """Replace 🏟️ in every /mercado user-panel path, including Staff test mode."""
    try:
        import manager_menu_patch as manager_menu
    except Exception as exc:
        print(f"WARNING AJAP escudo panel manager: no se pudo cargar manager_menu_patch: {exc}")
        return

    manager_menu.manager_panel_embed = _decorate_panel_with_badge(
        manager_menu.manager_panel_embed
    )

    # Staff dashboard stores the original user panel in a private cache. The
    # PERFIL USUARIO button reads this cache directly, so it must be decorated too.
    try:
        import staff_dashboard_patch as staff_dashboard

        cached = getattr(staff_dashboard, "_ORIGINAL_MANAGER_PANEL_EMBED", None)
        if callable(cached):
            staff_dashboard._ORIGINAL_MANAGER_PANEL_EMBED = _decorate_panel_with_badge(cached)
    except Exception as exc:
        print(f"WARNING AJAP escudo panel Staff: {exc}")

    # Staff profile gate also stores a prior panel reference for normal users.
    try:
        import staff_profile_gate_patch as staff_profiles

        cached = getattr(staff_profiles, "_PRIOR_MANAGER_PANEL", None)
        if callable(cached):
            staff_profiles._PRIOR_MANAGER_PANEL = _decorate_panel_with_badge(cached)
    except Exception as exc:
        print(f"WARNING AJAP escudo perfil usuario: {exc}")

    # Keep any runtime alias aligned as a final fallback.
    if APP is not None and callable(getattr(APP, "panel_embed", None)):
        APP.panel_embed = _decorate_panel_with_badge(APP.panel_embed)


def _install_vacancy_badge():
    """Show the corresponding club emoji in #equipos-libres vacancy cards."""
    try:
        import free_team_vacancy_patch as vacancies
    except Exception as exc:
        print(f"WARNING AJAP escudo vacantes: no se pudo cargar free_team_vacancy_patch: {exc}")
        return

    base_embed = getattr(vacancies, "vacancy_embed", None)
    base_publish = getattr(vacancies, "_publish_vacancy", None)
    if not callable(base_embed) or not callable(base_publish):
        return
    if getattr(base_embed, "_ajap_club_badge_title", False):
        return

    def vacancy_embed_with_badge(club: str):
        embed = base_embed(club)
        target_guild = _VACANCY_GUILD.get() or _current_guild()
        badge = _manual_badge_emoji(target_guild, club)
        if badge is not None and embed is not None:
            embed.title = f"📣 {badge} {club} está buscando DT!"
        return embed

    async def publish_vacancy_with_badge(guild, club: str):
        token = _VACANCY_GUILD.set(guild)
        try:
            return await base_publish(guild, club)
        finally:
            _VACANCY_GUILD.reset(token)

    vacancy_embed_with_badge._ajap_club_badge_title = True
    vacancy_embed_with_badge._ajap_club_badge_base = base_embed
    publish_vacancy_with_badge._ajap_club_badge_publish = True
    publish_vacancy_with_badge._ajap_club_badge_base = base_publish

    vacancies.vacancy_embed = vacancy_embed_with_badge
    vacancies._publish_vacancy = publish_vacancy_with_badge

    if APP is not None:
        APP.free_team_vacancy_embed = vacancy_embed_with_badge


async def _ensure_guild_badges(guild):
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
    _install_manager_panel_badge()
    _install_vacancy_badge()
    bot.add_listener(_check_manual_badges_on_ready, "on_ready")
    runtime._ajap_team_badge_selector_patch = True
    print("AJAP escudos manual-only activos en selector + panel + vacantes: City=:mancity: + Everton=:Everton: + Tottenham=:TOT: + Villarreal=:villa: + Real Betis=:betis: + Aston Villa=:aston: + Fulham=:FUL: + Sevilla=:SEV: + Celta de Vigo=:vigo: + PSG=:PSG: + Lyon=:lyon: + Marsella=:marcella: + Atletico=:atletico: + Middlesbrough=:middle: + Bolton=:bolton: + Ajax=:ajax: + Torino=:tor: + West Ham=:weh: + Newcastle=:newc: + Fiorentina=:fiore: + Lazio=:lazio: + Porto=:porto: + Benfica=:ben: + Zaragoza=:zara: + Galatasaray=:galata:")


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
