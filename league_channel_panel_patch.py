"""Configuración visual de canales de Liga desde el panel manager.

Agrega dentro de LIGA, solo para Staff, una pantalla para elegir:
- canal de resultados: el único canal cuyas capturas procesa el lector automático;
- canal de tablas: donde el bot mantiene tabla de posiciones y goleadores.

La configuración se guarda por servidor en league_config, reutilizando exactamente
la misma fuente que /liga_configurar y el listener automático existente.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import manager_menu_patch as manager


APP = None
BOT = None


def _runtime():
    return APP or manager.APP


def _bot():
    return BOT or manager.BOT


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
    runtime = _runtime()
    conn = league.db(runtime, int(guild_id))
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
    tables = cfg["table_channel_id"] if cfg else None

    embed = discord.Embed(
        title="⚙️ CANALES DE LIGA",
        description=(
            "Elegí de dónde toma los resultados y dónde publica las tablas. "
            "La configuración queda guardada para este servidor."
        ),
    )
    embed.add_field(
        name="📸 Canal de resultados",
        value=(
            f"{_mention(intake)}\n"
            "El bot solo procesa capturas enviadas en este canal."
        ),
        inline=False,
    )
    embed.add_field(
        name="🏆 Canal de tablas",
        value=(
            f"{_mention(tables)}\n"
            "Acá mantiene actualizadas la tabla de posiciones y goleadores."
        ),
        inline=False,
    )
    ready = bool(intake and tables)
    embed.add_field(
        name="Estado",
        value=(
            "✅ Automatización lista" if ready
            else "⚠️ Falta configurar uno o ambos canales"
        ),
        inline=False,
    )
    embed.set_footer(text="AJAP Liga • Configuración exclusiva de Staff")
    return embed


def league_hub_embeds(guild_id: int):
    runtime = _runtime()
    conn = league.db(runtime, int(guild_id))
    try:
        return [league.standings_embed(conn), league.scorers_embed(conn)]
    finally:
        conn.close()


def _save_intake(guild_id: int, channel_id: int):
    runtime = _runtime()
    conn = league.db(runtime, int(guild_id))
    try:
        league.schema(conn)
        conn.execute(
            """
            INSERT INTO league_config
                (guild_id, intake_channel_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                intake_channel_id = excluded.intake_channel_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (int(guild_id), int(channel_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _save_tables(guild_id: int, channel_id: int):
    runtime = _runtime()
    conn = league.db(runtime, int(guild_id))
    try:
        league.schema(conn)
        old = conn.execute(
            "SELECT table_channel_id FROM league_config WHERE guild_id = ?",
            (int(guild_id),),
        ).fetchone()
        old_id = int(old["table_channel_id"]) if old and old["table_channel_id"] else None
        changed = old_id != int(channel_id)
        conn.execute(
            """
            INSERT INTO league_config
                (guild_id, table_channel_id, standings_message_id, scorers_message_id, updated_at)
            VALUES (?, ?, NULL, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                table_channel_id = excluded.table_channel_id,
                standings_message_id = CASE WHEN ? THEN NULL ELSE league_config.standings_message_id END,
                scorers_message_id = CASE WHEN ? THEN NULL ELSE league_config.scorers_message_id END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (int(guild_id), int(channel_id), 1 if changed else 0, 1 if changed else 0),
        )
        conn.commit()
    finally:
        conn.close()


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


class TablesChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="🏆 Elegí el canal de tablas",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=1,
            custom_id="ajap_league_tables_channel",
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
            _save_tables(interaction.guild_id, channel.id)
            await interaction.response.edit_message(
                content=None,
                embeds=[league_config_embed(interaction.guild_id)],
                view=LeagueChannelConfigView(),
            )
            bot = _bot()
            if bot:
                try:
                    await league.refresh(_runtime(), bot, interaction.guild_id)
                except Exception as exc:
                    print(f"AJAP Liga refresh tras configurar tablas guild={interaction.guild_id}: {exc}")
        finally:
            _guild_reset(token)


class BackLeagueButton(discord.ui.Button):
    def __init__(self, row=2):
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
        self.add_item(TablesChannelSelect())
        self.add_item(BackLeagueButton(row=2))


class ConfigureLeagueChannelsButton(discord.ui.Button):
    def __init__(self, row=0):
        super().__init__(
            label="CONFIGURAR CANALES",
            emoji="⚙️",
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id="ajap_league_config_channels",
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


class LeagueHubView(discord.ui.View):
    def __init__(self, admin_mode=False):
        super().__init__(timeout=300)
        if admin_mode:
            self.add_item(ConfigureLeagueChannelsButton(row=0))
        self.add_item(manager.BackMainButton(row=1))


def install_league_channel_panel(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(manager, "_ajap_league_channel_panel_patch", False):
        return False

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
    print("AJAP Liga panel: configuración visual de canal resultados + canal tablas activa")
    return True


# Se importa después de manager_menu_patch. La clase ya existe y se puede parchear
# ahora; APP/BOT se enlazan durante apply_guild_isolation_patch.
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
