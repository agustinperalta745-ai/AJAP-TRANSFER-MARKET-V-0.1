"""Canal único de uso del mercado por servidor.

Un administrador ejecuta /canal_mercado dentro del canal deseado. Desde ese
momento, los comandos, botones, selects y modales del bot usados dentro del
servidor solo funcionan en ese canal. Los DMs siguen funcionando (por ejemplo,
notificaciones y acciones privadas) y los comandos/componentes de configuración
o flujos externos al mercado quedan exceptuados donde corresponde.

El canal interactivo del mercado NO depende del rol DT para poder abrir
/mercado. Esto es importante porque un usuario que renuncia deja de tener DT,
pero necesita seguir pudiendo entrar al mercado para elegir otro club.

Al iniciar/reconectar, el bot autocorrige el canal configurado y garantiza Ver
canal, Enviar mensajes, Leer historial y Usar comandos de aplicaciones. También
protege a usuarios que acaban de perder el rol DT con un allow individual si un
overwrite de otro rol todavía los bloqueara. El canal público/resumen de solo
lectura no se toca.
"""

import asyncio

import discord

APP = None
BOT = None
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


def _market_channel_id_for_ready(guild_id: int):
    """Lee la configuración desde la DB correcta aunque no haya interacción activa."""
    if APP is None:
        return None

    guild_context = getattr(APP, "guild_context", None)
    if guild_context is not None:
        try:
            with guild_context(int(guild_id)):
                return get_market_channel_id(int(guild_id))
        except Exception as exc:
            print(
                "WARNING AJAP canal mercado: no pude leer configuración con contexto "
                f"guild={guild_id} error={type(exc).__name__}: {exc}"
            )

    try:
        return get_market_channel_id(int(guild_id))
    except Exception as exc:
        print(
            "WARNING AJAP canal mercado: no pude leer configuración "
            f"guild={guild_id} error={type(exc).__name__}: {exc}"
        )
        return None


async def _resolve_text_channel(guild: discord.Guild, channel_id: int):
    channel = guild.get_channel(int(channel_id))
    if channel is None and BOT is not None:
        try:
            channel = await BOT.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            channel = None

    if not isinstance(channel, discord.TextChannel):
        return None
    if channel.guild.id != guild.id:
        return None
    return channel


def _market_allow(overwrite: discord.PermissionOverwrite):
    """Marca únicamente los permisos necesarios para usar /mercado."""
    dirty = False
    for name in (
        "view_channel",
        "send_messages",
        "read_message_history",
        "use_application_commands",
    ):
        if getattr(overwrite, name) is not True:
            setattr(overwrite, name, True)
            dirty = True
    return dirty


async def _ensure_member_market_access(
    guild: discord.Guild,
    channel: discord.TextChannel,
    member: discord.Member,
    *,
    reason: str,
):
    """Última defensa: un miembro concreto debe poder ejecutar /mercado."""
    if member.bot:
        return True

    perms = channel.permissions_for(member)
    if (
        perms.view_channel
        and perms.send_messages
        and perms.read_message_history
        and perms.use_application_commands
    ):
        return True

    me = guild.me
    if me is None or not channel.permissions_for(me).manage_channels:
        return False

    overwrite = channel.overwrites_for(member)
    _market_allow(overwrite)
    try:
        await channel.set_permissions(member, overwrite=overwrite, reason=reason)
        print(
            "AJAP canal mercado: acceso individual restaurado "
            f"guild={guild.id} channel={channel.id} user={member.id}"
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            "WARNING AJAP canal mercado: no pude restaurar acceso individual "
            f"guild={guild.id} channel={channel.id} user={member.id} "
            f"error={type(exc).__name__}: {exc}"
        )
        return False


async def _repair_market_channel_permissions(
    guild: discord.Guild,
    channel_id: int,
    *,
    reason: str,
):
    """Garantiza que /mercado siga accesible incluso sin rol DT."""
    channel = await _resolve_text_channel(guild, int(channel_id))
    if channel is None:
        print(
            "WARNING AJAP canal mercado: canal configurado no encontrado "
            f"guild={guild.id} channel={channel_id}"
        )
        return False

    me = guild.me
    if me is None:
        return False

    bot_perms = channel.permissions_for(me)
    if not bot_perms.manage_channels:
        print(
            "WARNING AJAP canal mercado: necesito Administrar canales para autocorregir "
            f"permisos | guild={guild.id} channel={channel.id}"
        )
        return False

    # /mercado es también la puerta de entrada para un usuario SIN club. Por eso
    # @everyone debe poder ver el canal y ejecutar el slash command. El rol DT
    # sigue representando al manager activo, pero ya no es la llave de acceso.
    targets = [guild.default_role]
    for target in channel.overwrites:
        if target == guild.default_role:
            continue
        if isinstance(target, (discord.Role, discord.Member)):
            targets.append(target)

    changed = []
    for target in targets:
        overwrite = channel.overwrites_for(target)
        dirty = False

        if target == guild.default_role:
            dirty = _market_allow(overwrite)
        else:
            # Un deny explícito en un rol/miembro puede ocultar los slash commands
            # aunque @everyone esté permitido. Solo convertimos denies de estos
            # cuatro permisos; el resto de permisos del canal no se toca.
            for name in (
                "view_channel",
                "send_messages",
                "read_message_history",
                "use_application_commands",
            ):
                if getattr(overwrite, name) is False:
                    setattr(overwrite, name, True)
                    dirty = True

        if not dirty:
            continue

        try:
            await channel.set_permissions(
                target,
                overwrite=overwrite,
                reason=reason,
            )
            changed.append(getattr(target, "name", str(getattr(target, "id", "?"))))
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(
                "WARNING AJAP canal mercado: Discord rechazó autocorrección "
                f"guild={guild.id} channel={channel.id} "
                f"target={getattr(target, 'id', '?')} "
                f"error={type(exc).__name__}: {exc}"
            )

    if changed:
        print(
            "AJAP canal mercado: permisos autocorregidos "
            f"guild={guild.id} channel={channel.id} targets={','.join(changed)}"
        )
    else:
        print(
            "AJAP canal mercado: permisos OK "
            f"guild={guild.id} channel={channel.id}"
        )
    return True


def _dt_role_removed(before: discord.Member, after: discord.Member) -> bool:
    """Detecta específicamente la pérdida del rol configurado como DT."""
    removed = {role.id for role in before.roles} - {role.id for role in after.roles}
    if not removed:
        return False
    try:
        import dt_role_patch as dt_roles

        role = dt_roles._dt_role(after.guild)
        return role is not None and role.id in removed
    except Exception:
        # Fallback seguro para servidores todavía no configurados: rol llamado DT.
        before_by_id = {role.id: role for role in before.roles}
        return any(
            (before_by_id[role_id].name or "").strip().casefold() == "dt"
            for role_id in removed
            if role_id in before_by_id
        )


def _install_permission_repair(bot):
    if getattr(bot, "_ajap_market_channel_permission_repair", False):
        return

    @bot.listen("on_ready")
    async def repair_market_channels_on_ready():
        # on_ready también puede dispararse tras una reconexión. La operación es
        # idempotente: si ya está bien, no modifica ningún overwrite.
        for guild in list(bot.guilds):
            channel_id = _market_channel_id_for_ready(guild.id)
            if not channel_id:
                continue
            try:
                repaired = await _repair_market_channel_permissions(
                    guild,
                    int(channel_id),
                    reason="AJAP: restaurar acceso general a /mercado",
                )
                if not repaired:
                    continue
                channel = await _resolve_text_channel(guild, int(channel_id))
                if channel is None:
                    continue

                # Si alguien ya había renunciado antes de este deploy, puede tener
                # un deny individual/heredado. Verificamos usuarios sin club y solo
                # creamos un allow personal cuando sus permisos efectivos fallan.
                guild_context = getattr(APP, "guild_context", None)
                for member in list(getattr(guild, "members", [])):
                    if member.bot:
                        continue
                    club = None
                    try:
                        if guild_context is not None:
                            with guild_context(int(guild.id)):
                                club = APP.club_de(member.id)
                        else:
                            club = APP.club_de(member.id)
                    except Exception:
                        club = None
                    if club:
                        continue
                    await _ensure_member_market_access(
                        guild,
                        channel,
                        member,
                        reason="AJAP: permitir /mercado a usuario sin club",
                    )
            except Exception as exc:
                print(
                    "WARNING AJAP canal mercado: error inesperado autocorrigiendo "
                    f"guild={guild.id} channel={channel_id} "
                    f"error={type(exc).__name__}: {exc}"
                )

    @bot.listen("on_member_update")
    async def repair_after_dt_role_removed(before: discord.Member, after: discord.Member):
        # La renuncia quita DT antes de borrar la asignación en SQLite. Detectamos
        # el rol directamente y restauramos acceso al instante, sin depender del
        # orden de esas dos operaciones.
        if after.bot or not _dt_role_removed(before, after):
            return
        channel_id = _market_channel_id_for_ready(after.guild.id)
        if not channel_id:
            return
        channel = await _resolve_text_channel(after.guild, int(channel_id))
        if channel is None:
            return
        await _ensure_member_market_access(
            after.guild,
            channel,
            after,
            reason="AJAP: conservar /mercado después de dejar el rol DT",
        )

    bot._ajap_market_channel_permission_repair = True


def apply_market_usage_channel_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
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

            # Si el canal estaba bloqueado por un overwrite viejo, arreglarlo en
            # el mismo momento de configurarlo. No toca el canal público/resumen.
            repaired = await _repair_market_channel_permissions(
                interaction.guild,
                interaction.channel.id,
                reason="AJAP: habilitar canal interactivo de mercado",
            )
            suffix = (
                "\n🔧 Acceso a `/mercado` verificado automáticamente, incluso sin rol DT."
                if repaired
                else "\n⚠️ Guardé el canal, pero no pude autocorregir permisos. "
                "El bot necesita **Administrar canales**."
            )
            await interaction.response.send_message(
                f"✅ **Canal del mercado configurado:** {interaction.channel.mention}\n"
                "Desde ahora, el uso del bot dentro del servidor queda limitado a este canal."
                + suffix,
                ephemeral=True,
            )

    _install_channel_gate(bot)
    _install_permission_repair(bot)
    runtime.market_usage_channel_id = get_market_channel_id
    runtime.repair_market_channel_permissions = _repair_market_channel_permissions
    runtime.ensure_member_market_access = _ensure_member_market_access
    runtime._ajap_market_usage_channel_patch = True
    print(
        "Canal único de mercado activo: /canal_mercado + acceso independiente de DT "
        "+ autocorrección de permisos"
    )
