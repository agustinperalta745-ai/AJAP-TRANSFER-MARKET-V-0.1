"""Canal único de uso del mercado por servidor.

Un administrador ejecuta /canal_mercado dentro del canal deseado. Desde ese
momento, los comandos, botones, selects y modales del bot usados dentro del
servidor solo funcionan en ese canal. Los DMs siguen funcionando (por ejemplo,
notificaciones y acciones privadas) y los comandos/componentes de configuración
o flujos externos al mercado quedan exceptuados donde corresponde.
"""

import asyncio

import discord

APP = None
EXEMPT_COMMANDS = {
    "canal_mercado",
    "canal_movimientos",
    "canal_equipos_libres",
    "rol_dt",
}

# Estos componentes viven deliberadamente fuera del canal de mercado.
# - Solicitar vacante: se usa en #equipos-libres.
# - Decisiones de vacante: se usan en el canal Staff/PES.
EXEMPT_COMPONENT_PREFIXES = (
    "ajap:free-team:apply:",
    "ajap:free-team-admin:",
)


def _ensure_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_usage_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            configured_by INTEGER,
            configured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def set_market_channel(guild_id: int, channel_id: int, user_id: int):
    with APP.db() as conn:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO market_usage_channels
            (guild_id, channel_id, configured_by, configured_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                configured_by = excluded.configured_by,
                updated_at = CURRENT_TIMESTAMP
            """,
            (int(guild_id), int(channel_id), int(user_id)),
        )


def get_market_channel_id(guild_id: int):
    with APP.db() as conn:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT channel_id FROM market_usage_channels WHERE guild_id = ?",
            (int(guild_id),),
        ).fetchone()
    return int(row["channel_id"]) if row else None


def _command_name(interaction):
    data = getattr(interaction, "data", None) or {}
    if isinstance(data, dict):
        name = data.get("name")
        return str(name) if name else None
    return None


def _component_is_exempt(custom_id) -> bool:
    value = str(custom_id or "")
    return any(value.startswith(prefix) for prefix in EXEMPT_COMPONENT_PREFIXES)


def _configured_wrong_channel(interaction):
    # DMs siguen funcionando: varias notificaciones del mercado son privadas.
    guild = getattr(interaction, "guild", None)
    guild_id = getattr(interaction, "guild_id", None)
    if not guild or not guild_id:
        return None

    # Estos comandos necesitan ejecutarse en el propio canal que se configura,
    # o son configuraciones de acceso que no pertenecen al flujo normal del mercado.
    if _command_name(interaction) in EXEMPT_COMMANDS:
        return None

    configured_id = get_market_channel_id(guild_id)
    if not configured_id:
        # Hasta que un admin ejecute /canal_mercado no bloqueamos el bot.
        return None

    current_id = getattr(interaction, "channel_id", None)
    if current_id is None:
        channel = getattr(interaction, "channel", None)
        current_id = getattr(channel, "id", None)

    return configured_id if int(current_id or 0) != configured_id else None


async def _deny_wrong_channel(interaction, channel_id: int):
    message = (
        f"⚠️ **El mercado solo puede utilizarse en <#{channel_id}>.**\n"
        "Entrá a ese canal y volvé a intentarlo."
    )
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


def _schedule_denial(interaction, channel_id: int):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_deny_wrong_channel(interaction, channel_id))
    except RuntimeError:
        pass


def _install_channel_gate(bot):
    tree = bot.tree
    original_tree_call = tree._call

    async def gated_tree_call(interaction):
        wrong_channel = _configured_wrong_channel(interaction)
        if wrong_channel:
            await _deny_wrong_channel(interaction, wrong_channel)
            return None
        return await original_tree_call(interaction)

    tree._call = gated_tree_call

    store = bot._connection._view_store
    original_dispatch_view = store.dispatch_view

    def gated_dispatch_view(component_type, custom_id, interaction):
        # Vacantes y sus decisiones administrativas viven fuera del mercado y
        # no deben pasar por la restricción de canal.
        if _component_is_exempt(custom_id):
            return original_dispatch_view(component_type, custom_id, interaction)

        wrong_channel = _configured_wrong_channel(interaction)
        if wrong_channel:
            _schedule_denial(interaction, wrong_channel)
            return None
        return original_dispatch_view(component_type, custom_id, interaction)

    store.dispatch_view = gated_dispatch_view

    original_dispatch_modal = getattr(store, "dispatch_modal", None)
    if original_dispatch_modal is not None:
        def gated_dispatch_modal(custom_id, interaction, components, *extra):
            if _component_is_exempt(custom_id):
                return original_dispatch_modal(custom_id, interaction, components, *extra)

            wrong_channel = _configured_wrong_channel(interaction)
            if wrong_channel:
                _schedule_denial(interaction, wrong_channel)
                return None
            return original_dispatch_modal(custom_id, interaction, components, *extra)

        store.dispatch_modal = gated_dispatch_modal


def apply_market_usage_channel_patch(runtime, bot):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_market_usage_channel_patch", False):
        return

    if bot.tree.get_command("canal_mercado") is None:
        @bot.tree.command(
            name="canal_mercado",
            description="Vincula este canal como único canal para usar el mercado",
        )
        async def canal_mercado(interaction: discord.Interaction):
            if not APP.es_admin(interaction):
                await interaction.response.send_message(
                    "⛔ Solo administradores pueden configurar el canal del mercado.",
                    ephemeral=True,
                )
                return
            if not interaction.guild or not interaction.channel:
                await interaction.response.send_message(
                    "⚠️ Este comando debe usarse dentro de un canal del servidor.",
                    ephemeral=True,
                )
                return
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message(
                    "⚠️ Elegí un canal de texto normal para usar el mercado.",
                    ephemeral=True,
                )
                return

            set_market_channel(
                interaction.guild.id,
                interaction.channel.id,
                interaction.user.id,
            )
            await interaction.response.send_message(
                f"✅ **Canal del mercado configurado:** {interaction.channel.mention}\n"
                "Desde ahora, el uso del bot dentro del servidor queda limitado a este canal.",
                ephemeral=True,
            )

    _install_channel_gate(bot)
    runtime.market_usage_channel_id = get_market_channel_id
    runtime._ajap_market_usage_channel_patch = True
    print("Canal único de mercado activo: /canal_mercado + bloqueo fuera del canal")
