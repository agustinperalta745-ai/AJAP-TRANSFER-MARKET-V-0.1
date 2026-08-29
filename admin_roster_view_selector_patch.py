"""Replace Staff -> Planteles -> Ver plantel text modal with a team selector.

The old callback asked Staff to type a club name and only acknowledged Discord
after querying the DB. On a guild's first access, DB migrations can take long
enough for Discord to expire the interaction. This patch acknowledges first,
then loads the active teams, uses exact club names from league_teams, and shows
the configured club crest emoji instead of the old country flag.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import staff_admin_organized_patch as staff
import team_badge_selector_patch as badges


APP = None
BOT = None


def _is_view_button(item) -> bool:
    if not isinstance(item, discord.ui.Button):
        return False
    label = str(getattr(item, "label", "") or "").strip().casefold()
    custom_id = str(getattr(item, "custom_id", "") or "").strip().casefold()
    return "ver plantel" in label or custom_id == "ajap_admin_roster_view"


def _club_emoji(guild, club: str):
    """Use the manual crest configured in this Discord server, never a flag."""
    badge = badges._manual_badge_emoji(guild, str(club or "").strip())
    return badge if badge is not None else "⚽"


def _active_teams():
    with APP.db() as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='league_teams' LIMIT 1"
        ).fetchone()
        if table:
            return conn.execute(
                """
                SELECT name, country
                FROM league_teams
                WHERE active = 1
                ORDER BY name COLLATE NOCASE
                LIMIT 25
                """
            ).fetchall()

        # Fallback for an old DB that has not created league_teams yet.
        return conn.execute(
            """
            SELECT club AS name, '' AS country
            FROM roster_players
            WHERE TRIM(COALESCE(club,'')) != ''
            GROUP BY club COLLATE NOCASE
            ORDER BY club COLLATE NOCASE
            LIMIT 25
            """
        ).fetchall()


def _selector_embed():
    embed = discord.Embed(
        title="📋 VER PLANTEL",
        description=(
            "Elegí el equipo que querés consultar.\n"
            "Ya no hace falta escribir el nombre del club manualmente."
        ),
    )
    embed.set_footer(text="AJAP Transfer Market • Planteles Staff")
    return embed


def _rosters_embed():
    return staff.section_embed(
        "👥 PLANTELES",
        "Correcciones sobre los planteles oficiales.",
        ["➕ Agregar jugador", "🔁 Mover jugador", "🗑️ Quitar jugador", "📋 Ver plantel"],
    )


class RosterTeamSelect(discord.ui.Select):
    def __init__(self, rows, guild=None):
        options = [
            discord.SelectOption(
                label=str(row["name"])[:100],
                description=(str(row["country"]) or "Equipo activo")[:100],
                value=str(row["name"]),
                emoji=_club_emoji(guild, row["name"]),
            )
            for row in rows[:25]
        ]
        super().__init__(
            placeholder="Elegí el equipo",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ajap_admin_roster_view_team_select",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        # Acknowledge immediately. Building the embed can trigger a first-use DB
        # migration in this guild, so never leave Discord waiting for that work.
        await interaction.response.defer()
        club = str(self.values[0]).strip()
        try:
            embed = APP.plantel_embed(club)
            rows = _active_teams()
            await interaction.edit_original_response(
                embed=embed,
                view=RosterTeamView(rows, guild=interaction.guild),
            )
        except Exception as exc:
            print(f"AJAP VER PLANTEL error ({club}): {exc!r}")
            error = discord.Embed(
                title="⚠️ No pude cargar el plantel",
                description=(
                    f"Falló la consulta de **{club}**. La interacción quedó respondida "
                    "para evitar el error de tiempo de Discord."
                ),
                color=discord.Color.orange(),
            )
            await interaction.edit_original_response(embed=error, view=None)


class BackToRostersButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="VOLVER",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=1,
            custom_id="ajap_admin_roster_view_back",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[_rosters_embed()],
            view=staff.RostersView(),
        )


class RosterTeamView(discord.ui.View):
    def __init__(self, rows, guild=None):
        super().__init__(timeout=300)
        if rows:
            self.add_item(RosterTeamSelect(rows, guild=guild))
        self.add_item(BackToRostersButton())


class ViewRosterSelectorButton(discord.ui.Button):
    def __init__(self, source_button):
        super().__init__(
            label=getattr(source_button, "label", None) or "VER PLANTEL",
            emoji=getattr(source_button, "emoji", None) or "📋",
            style=getattr(source_button, "style", discord.ButtonStyle.secondary),
            disabled=bool(getattr(source_button, "disabled", False)),
            row=getattr(source_button, "row", None),
            custom_id="ajap_admin_roster_view",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        # The old button opened a modal immediately and the modal then queried
        # the DB before replying. Defer first so even a slow first migration is safe.
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            rows = _active_teams()
            if not rows:
                await interaction.followup.send(
                    "⚠️ No hay equipos activos para consultar.",
                    ephemeral=True,
                )
                return
            await interaction.followup.send(
                embed=_selector_embed(),
                view=RosterTeamView(rows, guild=interaction.guild),
                ephemeral=True,
            )
        except Exception as exc:
            print(f"AJAP VER PLANTEL selector error: {exc!r}")
            await interaction.followup.send(
                "⚠️ No pude abrir la lista de equipos. La interacción fue respondida correctamente; revisá los logs del bot para el detalle.",
                ephemeral=True,
            )


def _install_roster_view_selector():
    BaseRostersView = staff.RostersView
    if getattr(BaseRostersView, "_ajap_roster_view_selector", False):
        return

    class SelectorRostersView(BaseRostersView):
        def __init__(self):
            super().__init__()
            original_items = list(self.children)
            self.clear_items()
            for item in original_items:
                if _is_view_button(item):
                    self.add_item(ViewRosterSelectorButton(item))
                else:
                    self.add_item(item)

    SelectorRostersView.__name__ = "RostersView"
    SelectorRostersView._ajap_roster_view_selector = True
    staff.RostersView = SelectorRostersView


def apply_admin_roster_view_selector_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_admin_roster_view_selector_patch", False):
        return

    _install_roster_view_selector()
    runtime._ajap_admin_roster_view_selector_patch = True
    print("AJAP Staff: Ver plantel usa selector con escudos + defer anti-timeout")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_roster_view_selector(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_admin_roster_view_selector_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_admin_roster_view_selector_wrapped",
    False,
):
    _apply_guild_isolation_then_roster_view_selector._ajap_admin_roster_view_selector_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_roster_view_selector
