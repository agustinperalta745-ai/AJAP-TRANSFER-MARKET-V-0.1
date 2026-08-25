"""Hide administrative market controls from regular AJAP players.

Security checks already protect the callbacks. This patch adds the UX layer:
regular players never receive Administration/Assignments buttons in their
personal market menu, while Discord administrators keep both controls.
The /mercado panel is ephemeral so an admin's private controls are never exposed
visually to other members in the channel.
"""

import discord

import navigation_patch as navigation
import team_assignment as teams


APP = None
BOT = None
ADMIN_CUSTOM_IDS = {"mercado_admin", "mercado_asignaciones"}
ADMIN_LABELS = {"Administración", "Asignaciones"}


def market_view_for(interaction: discord.Interaction):
    """Build the final market view and remove admin-only controls for players."""
    view = APP.MercadoView()
    if APP.es_admin(interaction):
        return view

    for item in list(view.children):
        custom_id = getattr(item, "custom_id", None)
        label = getattr(item, "label", None)
        if custom_id in ADMIN_CUSTOM_IDS or label in ADMIN_LABELS:
            view.remove_item(item)
    return view


async def filtered_mercado_command(interaction: discord.Interaction):
    if not teams.club_de(interaction.user.id):
        await interaction.response.send_message(
            embed=teams.welcome_embed(),
            view=teams.TeamChoiceView(),
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        embed=APP.panel_embed(interaction.user.id),
        view=market_view_for(interaction),
        ephemeral=True,
    )


async def filtered_team_select_callback(self, interaction: discord.Interaction):
    current = teams.club_de(interaction.user.id)
    if current:
        await interaction.response.send_message(
            f"⚠️ Ya tenés asignado **{current}**. Solo un admin puede revertirlo.",
            ephemeral=True,
        )
        return

    ok, result = teams.assign_team(interaction.user.id, self.values[0])
    if not ok:
        await interaction.response.send_message(f"⚠️ {result}", ephemeral=True)
        return

    jugadores = APP.jugadores_de_club(result, 50)
    await interaction.response.edit_message(
        embed=discord.Embed(
            title=f"✅ {result} asignado",
            description=(
                f"Desde ahora manejás **{result}**.\n\n"
                f"Plantilla cargada: **{len(jugadores)} jugadores**.\n"
                "Ya podés entrar a **Mi club** o **Publicar jugador** para usar el mercado."
            ),
        ),
        view=market_view_for(interaction),
    )


async def filtered_main_menu_callback(self, interaction: discord.Interaction):
    await interaction.response.edit_message(
        content=None,
        embed=self.runtime.panel_embed(interaction.user.id),
        view=market_view_for(interaction),
    )


def apply_admin_visibility_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_admin_visibility_patch", False):
        return

    # /mercado is re-registered after every other UI patch, so it always builds
    # the final view and filters it for the requesting member.
    bot.tree.remove_command("mercado")
    bot.tree.command(
        name="mercado",
        description="Abre el panel principal de AJAP Transfer Market",
    )(filtered_mercado_command)

    # The first menu shown immediately after choosing a club must be filtered too.
    teams.TeamSelect.callback = filtered_team_select_callback

    # Every navigational 'Volver al menú' button also rebuilds a user-specific view.
    navigation.MainMenuButton.callback = filtered_main_menu_callback

    runtime.market_view_for = market_view_for
    runtime._ajap_admin_visibility_patch = True
    print("AJAP visibilidad admin activa: Administración/Asignaciones ocultas para jugadores")
