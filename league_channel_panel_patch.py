"""Liga AJAP: un solo canal de resultados y tablas dentro del menú.

El bot escucha capturas únicamente en el canal de resultados configurado.
La tabla de posiciones y goleadores NO se publican en ningún canal: se leen
siempre en vivo desde la DB al abrir LIGA dentro del panel manager.
"""

from __future__ import annotations

import os

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import manager_menu_patch as manager


APP = None
BOT = None


def _runtime():
    return APP or manager.APP


def _is_admin(interaction: discord.Interaction) -> bool:
    runtime = _runtime()
    return bool(runtime and runtime.es_admin(interaction))


def _guild_token(interaction: discord.Interaction):
    return guild_isolation._CURRENT_GUILD_ID.set(
        guild_isolation._interaction_guild_id(interaction)
    )


def _guild_reset(token):
    guild_isolation._CURRENT_GUILD_ID.reset(token)


def _config(guild_id: int):
    conn = league.db(_runtime(), int(guild_id))
    try:
        return conn.execute(
            "SELECT * FROM league_config WHERE guild_id = ?",
            (int(guild_id),),
        ).fetchone()
    finally:
        conn.close()


def _mention(channel_id):
    return f"<#{int(channel_id)}>" if channel_id else "Sin configurar"


def league_config_embed(guild_id: int):
    cfg = _config(guild_id)
    intake = cfg["intake_channel_id"] if cfg else None
    embed = discord.Embed(
        title="⚙️ CANAL DE RESULTADOS",
        description=(
            "Elegí el canal donde los usuarios van a subir las capturas de los partidos. "
            "El bot toma resultados únicamente desde ese canal."
        ),
    )
    embed.add_field(
        name="📸 Canal de resultados",
        value=f"{_mention(intake)}\nEl bot procesa las capturas enviadas acá.",
        inline=False,
    )
    embed.add_field(
        name="🏆 Tabla y goleadores",
        value="Se muestran y actualizan directamente dentro de **LIGA** en el menú.",
        inline=False,
    )
    embed.add_field(
        name="Estado",
        value="✅ Automatización lista" if intake else "⚠️ Falta elegir el canal de resultados",
        inline=False,
    )
    embed.set_footer(text="AJAP Liga • Configuración exclusiva de Staff")
    return embed


def league_hub_embeds(guild_id: int):
    conn = league.db(_runtime(), int(guild_id))
    try:
        standings = league.standings_embed(conn)
        scorers = league.scorers_embed(conn)
        standings.set_footer(text="AJAP Liga • Datos actualizados al abrir esta pantalla")
        scorers.set_footer(text="AJAP Liga • Datos actualizados al abrir esta pantalla")
        return [standings, scorers]
    finally:
        conn.close()


def _save_intake(guild_id: int, channel_id: int):
    conn = league.db(_runtime(), int(guild_id))
    try:
        league.schema(conn)
        conn.execute(
            """
            INSERT INTO league_config
                (guild_id, intake_channel_id, table_channel_id,
                 standings_message_id, scorers_message_id, updated_at)
            VALUES (?, ?, NULL, NULL, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                intake_channel_id = excluded.intake_channel_id,
                table_channel_id = NULL,
                standings_message_id = NULL,
                scorers_message_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (int(guild_id), int(channel_id)),
        )
        conn.commit()
    finally:
        conn.close()


async def _menu_only_refresh(runtime, bot, guild_id):
    """No publica tablas en canales; LIGA siempre las renderiza desde la DB."""
    return None


class ResultsChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="📸 Elegí el canal de resultados",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=0,
            custom_id="ajap_league_results_channel",
        )

    async def callback(self, interaction: discord.Interaction):
        token = _guild_token(interaction)
        try:
            if not _is_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            if not interaction.guild_id:
                await interaction.response.send_message("⚠️ La Liga solo funciona dentro del servidor.", ephemeral=True)
                return
            channel = self.values[0]
            _save_intake(interaction.guild_id, channel.id)
            await interaction.response.edit_message(
                content=None,
                embeds=[league_config_embed(interaction.guild_id)],
                view=LeagueChannelConfigView(),
            )
        finally:
            _guild_reset(token)


class BackLeagueButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="VOLVER A LIGA",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_league_back_hub",
        )

    async def callback(self, interaction: discord.Interaction):
        token = _guild_token(interaction)
        try:
            await interaction.response.edit_message(
                content=None,
                embeds=league_hub_embeds(interaction.guild_id),
                view=LeagueHubView(admin_mode=_is_admin(interaction)),
            )
        finally:
            _guild_reset(token)


class LeagueChannelConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(ResultsChannelSelect())
        self.add_item(BackLeagueButton(row=1))


class ConfigureLeagueChannelButton(discord.ui.Button):
    def __init__(self, row=0):
        super().__init__(
            label="CONFIGURAR RESULTADOS",
            emoji="⚙️",
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id="ajap_league_config_results",
        )

    async def callback(self, interaction: discord.Interaction):
        token = _guild_token(interaction)
        try:
            if not _is_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            await interaction.response.edit_message(
                content=None,
                embeds=[league_config_embed(interaction.guild_id)],
                view=LeagueChannelConfigView(),
            )
        finally:
            _guild_reset(token)


class RefreshLeagueButton(discord.ui.Button):
    def __init__(self, row=0):
        super().__init__(
            label="ACTUALIZAR",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_league_refresh_menu",
        )

    async def callback(self, interaction: discord.Interaction):
        token = _guild_token(interaction)
        try:
            await interaction.response.edit_message(
                content=None,
                embeds=league_hub_embeds(interaction.guild_id),
                view=LeagueHubView(admin_mode=_is_admin(interaction)),
            )
        finally:
            _guild_reset(token)


class LeagueHubView(discord.ui.View):
    def __init__(self, admin_mode=False):
        super().__init__(timeout=300)
        self.add_item(RefreshLeagueButton(row=0))
        if admin_mode:
            self.add_item(ConfigureLeagueChannelButton(row=0))
        self.add_item(manager.BackMainButton(row=1))


def _replace_slash_commands(runtime, bot):
    bot.tree.remove_command("liga_configurar")

    @bot.tree.command(
        name="liga_configurar",
        description="Configura el canal de resultados de la Liga AJAP",
    )
    async def liga_configurar(
        interaction: discord.Interaction,
        canal_resultados: discord.TextChannel,
    ):
        if not league.admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        _save_intake(interaction.guild_id, canal_resultados.id)
        await interaction.response.send_message(
            f"✅ Canal de resultados configurado: {canal_resultados.mention}. "
            "La tabla y los goleadores se consultan desde 🏆 LIGA.",
            ephemeral=True,
        )

    bot.tree.remove_command("liga_estado")

    @bot.tree.command(name="liga_estado", description="Muestra el estado del módulo Liga")
    async def liga_estado(interaction: discord.Interaction):
        if not league.admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        conn = league.db(runtime, interaction.guild_id)
        try:
            cfg = conn.execute(
                "SELECT * FROM league_config WHERE guild_id = ?",
                (interaction.guild_id,),
            ).fetchone()
            matches = conn.execute("SELECT COUNT(*) AS n FROM league_matches").fetchone()["n"]
            goals = conn.execute("SELECT COALESCE(SUM(goals),0) AS n FROM league_goal_events").fetchone()["n"]
        finally:
            conn.close()
        intake = _mention(cfg["intake_channel_id"] if cfg else None)
        api = "✅ configurada" if os.getenv("OPENAI_API_KEY") else "❌ falta OPENAI_API_KEY"
        embed = discord.Embed(
            title="📊 Estado Liga AJAP",
            description=(
                f"📸 Canal de resultados: {intake}\n"
                f"🏆 Tabla: **dentro del menú LIGA**\n"
                f"🤖 Visión: {api}\n"
                f"⚽ Partidos cargados: **{matches}**\n"
                f"🥅 Goles acumulados: **{goals}**\n"
                f"🎯 Confianza mínima: **{league.MIN_CONF:.0%}**"
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


def install_league_channel_panel(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(manager, "_ajap_league_channel_panel_patch", False):
        return False

    # Deshabilita definitivamente cualquier publicación automática de tablas.
    league.refresh = _menu_only_refresh
    _replace_slash_commands(runtime, bot)

    async def league_button_callback(self, interaction: discord.Interaction):
        token = _guild_token(interaction)
        try:
            if not interaction.guild_id:
                await interaction.response.send_message(
                    "⚠️ La Liga solo está disponible dentro del servidor.",
                    ephemeral=True,
                )
                return
            await interaction.response.edit_message(
                content=None,
                embeds=league_hub_embeds(interaction.guild_id),
                view=LeagueHubView(admin_mode=_is_admin(interaction)),
            )
        finally:
            _guild_reset(token)

    manager.LeagueButton.callback = league_button_callback
    runtime.LeagueHubView = LeagueHubView
    manager._ajap_league_channel_panel_patch = True
    print("AJAP Liga: un canal de resultados + tabla/goleadores solo dentro del menú")
    return True


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_league_channels(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    install_league_channel_panel(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_league_channel_panel_wrapped",
    False,
):
    _apply_guild_isolation_then_league_channels._ajap_league_channel_panel_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_league_channels
