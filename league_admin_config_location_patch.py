"""Mueve la configuración de resultados de Liga al panel de Administración.

El menú 🏆 LIGA de los jugadores queda exclusivamente para consultar tabla y
goleadores. La selección del canal de resultados vive en Administración -> Gestión.
"""

from __future__ import annotations

import discord

import league_channel_panel_patch as league_ui
import staff_admin_organized_patch as staff


class PlayerLeagueView(discord.ui.View):
    """Vista pública de Liga: consulta solamente, incluso si quien entra es admin."""

    def __init__(self, admin_mode=False):
        super().__init__(timeout=300)
        self.add_item(league_ui.RefreshLeagueButton(row=0))
        self.add_item(league_ui.manager.BackMainButton(row=1))


class BackManagementButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="VOLVER A GESTIÓN",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_admin_league_back_management",
        )

    async def callback(self, interaction: discord.Interaction):
        if not staff.APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        embed = staff.section_embed(
            "⚙️ GESTIÓN",
            "Configuración general del torneo y del mercado.",
            [
                "👥 Asignaciones",
                "🗓️ Cambiar temporada",
                "📤 Exportar mercado",
                "🏆 Configurar resultados de Liga",
            ],
        )
        await interaction.response.edit_message(
            content=None,
            embeds=[embed],
            view=staff.ManagementView(),
        )


class AdminResultsChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="📸 Elegí el canal de resultados",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=0,
            custom_id="ajap_admin_league_results_channel",
        )

    async def callback(self, interaction: discord.Interaction):
        token = league_ui._guild_token(interaction)
        try:
            if not staff.APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            if not interaction.guild_id:
                await interaction.response.send_message(
                    "⚠️ La Liga solo funciona dentro del servidor.", ephemeral=True
                )
                return
            channel = self.values[0]
            league_ui._save_intake(interaction.guild_id, channel.id)
            await interaction.response.edit_message(
                content=None,
                embeds=[league_ui.league_config_embed(interaction.guild_id)],
                view=AdminLeagueConfigView(),
            )
        finally:
            league_ui._guild_reset(token)


class AdminLeagueConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(AdminResultsChannelSelect())
        self.add_item(BackManagementButton(row=1))


class AdminConfigureResultsButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="CONFIGURAR RESULTADOS",
            emoji="🏆",
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id="ajap_admin_league_config_results",
        )

    async def callback(self, interaction: discord.Interaction):
        token = league_ui._guild_token(interaction)
        try:
            if not staff.APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            await interaction.response.edit_message(
                content=None,
                embeds=[league_ui.league_config_embed(interaction.guild_id)],
                view=AdminLeagueConfigView(),
            )
        finally:
            league_ui._guild_reset(token)


# 1) Nunca mostrar configuración dentro del menú LIGA de jugadores.
league_ui.LeagueHubView = PlayerLeagueView

# 2) Agregar la herramienta al bloque Administración -> Gestión.
_ORIGINAL_MANAGEMENT_VIEW = staff.ManagementView


class ManagementViewWithLeague(_ORIGINAL_MANAGEMENT_VIEW):
    def __init__(self):
        super().__init__()
        self.add_item(AdminConfigureResultsButton(row=1))


staff.ManagementView = ManagementViewWithLeague

# 3) Reflejar la herramienta también en la descripción de Gestión.
_original_section_embed = staff.section_embed


def _section_embed_with_league(title, description, tools):
    items = list(tools)
    if "GESTIÓN" in str(title).upper() and not any("resultado" in str(x).casefold() for x in items):
        items.append("🏆 Configurar resultados de Liga")
    return _original_section_embed(title, description, items)


staff.section_embed = _section_embed_with_league

print("AJAP Liga: configurar resultados movido de menú jugador a Administración -> Gestión")
