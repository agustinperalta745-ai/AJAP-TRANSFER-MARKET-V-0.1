"""Formas explícitas de vincular y diagnosticar el canal público del mercado.

- /canal_publico_mercado vincula directamente el canal donde se ejecuta.
- /vincular_resumen_mercado queda como alias por compatibilidad.
- /probar_resumen_mercado verifica permisos, publica una prueba real y fuerza el
  backfill de rumores pendientes que hayan quedado sin anunciar.

La configuración es independiente del canal Staff/PES.
"""

from __future__ import annotations

import discord

import market_usage_channel_patch as market_usage
import public_market_summary_patch as public_summary


# Estos comandos son de CONFIGURACIÓN/DIAGNÓSTICO y justamente deben poder
# ejecutarse fuera del canal único de uso del mercado.
market_usage.EXEMPT_COMMANDS.update(
    {
        "canal_publico_mercado",
        "vincular_resumen_mercado",
        "canal_resumen_mercado",
        "probar_resumen_mercado",
    }
)

_ORIGINAL_APPLY = public_summary.apply_public_market_summary_patch


def _can_publish(runtime, interaction: discord.Interaction, canal: discord.TextChannel):
    if not runtime.es_admin(interaction):
        return False, "⛔ Solo administradores."
    if interaction.guild is None:
        return False, "⚠️ Este comando solo funciona dentro de un servidor."
    if canal.guild.id != interaction.guild.id:
        return False, "⚠️ Elegí un canal de este mismo servidor."

    me = interaction.guild.me
    if me is not None:
        perms = canal.permissions_for(me)
        if not perms.view_channel or not perms.send_messages:
            return (
                False,
                f"⚠️ No puedo publicar en {canal.mention}. Dame **Ver canal** y **Enviar mensajes**.",
            )
    return True, None


async def _save_channel(runtime, interaction: discord.Interaction, canal: discord.TextChannel):
    ok, error = _can_publish(runtime, interaction, canal)
    if not ok:
        await interaction.response.send_message(error, ephemeral=True)
        return

    public_summary.set_public_channel(
        interaction.guild.id,
        canal.id,
        interaction.user.id,
    )
    await interaction.response.send_message(
        f"✅ **Canal público del mercado vinculado:** {canal.mention}\n"
        "Rumores, transferencias, préstamos, intercambios, clausulazos y opciones de compra "
        "se anunciarán ahí. El canal Staff/PES no se modifica.",
        ephemeral=True,
    )


async def _bind_current_channel(runtime, interaction: discord.Interaction):
    if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "⚠️ Usá este comando dentro del canal de texto que querés vincular.",
            ephemeral=True,
        )
        return
    await _save_channel(runtime, interaction, interaction.channel)


def _normalize(name: str) -> str:
    return "".join(ch for ch in str(name or "").casefold() if ch.isalnum())


async def _resolve_diagnostic_channel(guild):
    configured_id = None
    try:
        configured_id = public_summary.get_public_channel_id(guild.id)
    except Exception as exc:
        print(f"WARNING AJAP: diagnóstico resumen no pudo leer configuración: {exc}")

    if configured_id:
        channel = guild.get_channel(int(configured_id))
        if channel is None:
            try:
                channel = await public_summary.APP.bot.fetch_channel(int(configured_id))
            except Exception:
                channel = None
        if channel is not None and hasattr(channel, "send"):
            return channel, configured_id, "CONFIGURADO"

    accepted = {"resumenmercado", "resumendemercado", "mercadoresumen"}
    for channel in getattr(guild, "text_channels", []):
        if _normalize(getattr(channel, "name", "")) in accepted:
            return channel, configured_id, "POR_NOMBRE"

    return None, configured_id, "NO_ENCONTRADO"


async def _diagnose_and_force(runtime, interaction: discord.Interaction):
    if not runtime.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return
    if interaction.guild is None:
        await interaction.response.send_message(
            "⚠️ Este comando solo funciona dentro de un servidor.", ephemeral=True
        )
        return

    # Acknowledge immediately: the backfill may need several Discord sends.
    await interaction.response.defer(ephemeral=True, thinking=True)

    channel, configured_id, source = await _resolve_diagnostic_channel(interaction.guild)
    if channel is None:
        await interaction.followup.send(
            "❌ **No encontré un destino para el resumen.**\n"
            f"Canal guardado en DB: `{configured_id or 'ninguno'}`.\n"
            "Ejecutá `/canal_publico_mercado` dentro de #RESUMEN-MERCADO.",
            ephemeral=True,
        )
        return

    me = interaction.guild.me
    perms = channel.permissions_for(me) if me is not None else None
    can_view = bool(perms.view_channel) if perms is not None else True
    can_send = bool(perms.send_messages) if perms is not None else True
    can_embed = bool(perms.embed_links) if perms is not None else True

    if not can_view or not can_send:
        await interaction.followup.send(
            f"❌ Encontré {channel.mention}, pero el bot no puede publicar ahí.\n"
            f"Ver canal: **{'Sí' if can_view else 'NO'}** • "
            f"Enviar mensajes: **{'Sí' if can_send else 'NO'}** • "
            f"Insertar enlaces/embeds: **{'Sí' if can_embed else 'NO'}**",
            ephemeral=True,
        )
        return

    mode = "EMBED"
    test_message = None
    test_embed = discord.Embed(
        title="🧪 RESUMEN DE MERCADO CONECTADO",
        description=(
            "El bot puede publicar correctamente en este canal. "
            "Ahora voy a recuperar los rumores pendientes que falten."
        ),
        color=discord.Color.green(),
    )
    test_embed.set_footer(text="AJAP Transfer Market • Prueba de conexión")

    try:
        test_message = await channel.send(
            embed=test_embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException) as embed_exc:
        mode = "TEXTO"
        print(f"WARNING AJAP: prueba embed resumen falló: {embed_exc}")
        try:
            test_message = await channel.send(
                "🧪 **RESUMEN DE MERCADO CONECTADO**\n"
                "El bot puede publicar correctamente en este canal. "
                "Ahora voy a recuperar los rumores pendientes que falten.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException) as text_exc:
            await interaction.followup.send(
                f"❌ Discord rechazó el envío a {channel.mention}: `{type(text_exc).__name__}`.\n"
                "Revisá que el bot tenga **Ver canal** y **Enviar mensajes**.",
                ephemeral=True,
            )
            print(f"WARNING AJAP: prueba texto resumen también falló: {text_exc}")
            return

    recovered = "NO_EJECUTADO"
    try:
        import market_rumor_patch as market_rumor

        await market_rumor._backfill_pending_rumors()
        recovered = "EJECUTADO"
    except Exception as exc:
        recovered = f"ERROR {type(exc).__name__}"
        print(f"WARNING AJAP: forzado de rumores pendientes falló: {exc}")

    # Persist the discovered channel too, even when it was found by name. This
    # repairs stale/missing configuration without requiring a second command.
    try:
        public_summary.set_public_channel(
            interaction.guild.id,
            channel.id,
            interaction.user.id,
        )
    except Exception as exc:
        print(f"WARNING AJAP: diagnóstico no pudo persistir canal público: {exc}")

    await interaction.followup.send(
        f"✅ **Prueba enviada a {channel.mention}.**\n"
        f"Origen: **{source}** • Envío: **{mode}** • "
        f"Backfill: **{recovered}** • Mensaje: `{getattr(test_message, 'id', '—')}`",
        ephemeral=True,
    )


def _register_explicit_channel_commands(runtime, bot):
    registered = []

    # Si una versión anterior dejó el comando local con parámetro obligatorio,
    # lo quitamos del árbol local y registramos la variante simple. El próximo
    # bot.tree.sync() reemplaza la definición global en Discord.
    existing = bot.tree.get_command("canal_publico_mercado")
    if existing is not None:
        bot.tree.remove_command("canal_publico_mercado")

    @bot.tree.command(
        name="canal_publico_mercado",
        description="Vincula este canal como resumen público del mercado",
    )
    async def canal_publico_mercado(interaction: discord.Interaction):
        await _bind_current_channel(runtime, interaction)

    registered.append("/canal_publico_mercado")

    if bot.tree.get_command("vincular_resumen_mercado") is None:
        @bot.tree.command(
            name="vincular_resumen_mercado",
            description="Vincula este canal como resumen público del mercado",
        )
        async def vincular_resumen_mercado(interaction: discord.Interaction):
            await _bind_current_channel(runtime, interaction)

        registered.append("/vincular_resumen_mercado")

    if bot.tree.get_command("probar_resumen_mercado") is None:
        @bot.tree.command(
            name="probar_resumen_mercado",
            description="Prueba el resumen público y recupera rumores pendientes",
        )
        async def probar_resumen_mercado(interaction: discord.Interaction):
            await _diagnose_and_force(runtime, interaction)

        registered.append("/probar_resumen_mercado")

    return registered


def apply_with_explicit_selector(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    registered = _register_explicit_channel_commands(runtime, bot)
    if registered:
        print("AJAP canal público: comandos activos " + ", ".join(registered))


if not getattr(public_summary, "_ajap_explicit_public_channel_selector", False):
    public_summary.apply_public_market_summary_patch = apply_with_explicit_selector
    public_summary._ajap_explicit_public_channel_selector = True
