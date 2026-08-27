"""Formas explícitas de vincular y diagnosticar el canal público del mercado.

- /canal_publico_mercado vincula directamente el canal donde se ejecuta.
- /vincular_resumen_mercado queda como alias por compatibilidad.
- /probar_resumen_mercado toma COMO DESTINO el canal donde se ejecuta, lo guarda,
  verifica el guardado, publica una prueba real y fuerza el backfill de rumores.

La configuración es independiente del canal Staff/PES.
"""

from __future__ import annotations

import discord

import market_usage_channel_patch as market_usage
import public_market_summary_patch as public_summary


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


def _persist_and_verify(interaction: discord.Interaction, canal: discord.TextChannel):
    """Guarda el canal en la DB explícita del guild y verifica el round-trip."""
    public_summary.set_public_channel(
        interaction.guild.id,
        canal.id,
        interaction.user.id,
    )
    saved = public_summary.get_public_channel_id(interaction.guild.id)
    return int(saved) == int(canal.id), saved


async def _save_channel(runtime, interaction: discord.Interaction, canal: discord.TextChannel):
    ok, error = _can_publish(runtime, interaction, canal)
    if not ok:
        await interaction.response.send_message(error, ephemeral=True)
        return

    try:
        persisted, saved = _persist_and_verify(interaction, canal)
    except Exception as exc:
        print(f"WARNING AJAP: no pude guardar canal público: {exc}")
        await interaction.response.send_message(
            f"❌ No pude guardar el canal público: `{type(exc).__name__}`.",
            ephemeral=True,
        )
        return

    if not persisted:
        await interaction.response.send_message(
            f"❌ Intenté guardar {canal.mention}, pero la DB devolvió `{saved}`. "
            "No voy a marcarlo como configurado hasta que el guardado sea real.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"✅ **Canal público del mercado vinculado:** {canal.mention}\n"
        f"Guardado verificado en DB: `{saved}`.\n"
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

    # Fallback más tolerante para otras rutas: revisa todos los canales del guild,
    # no solamente guild.text_channels, y acepta nombres que contengan ambos términos.
    for channel in getattr(guild, "channels", []):
        if not hasattr(channel, "send"):
            continue
        normalized = _normalize(getattr(channel, "name", ""))
        if "resumen" in normalized and "mercado" in normalized:
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
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "⚠️ Ejecutá este comando dentro de #RESUMEN-MERCADO.", ephemeral=True
        )
        return

    # La prueba se ejecuta DENTRO del canal destino. No tiene sentido volver a
    # buscarlo por nombre: el canal actual es la fuente de verdad y se guarda ahora.
    channel = interaction.channel
    ok, error = _can_publish(runtime, interaction, channel)
    if not ok:
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    previous_id = None
    try:
        previous_id = public_summary.get_public_channel_id(interaction.guild.id)
    except Exception as exc:
        print(f"WARNING AJAP: diagnóstico no pudo leer canal previo: {exc}")

    try:
        persisted, saved_id = _persist_and_verify(interaction, channel)
    except Exception as exc:
        print(f"WARNING AJAP: diagnóstico no pudo guardar canal actual: {exc}")
        await interaction.followup.send(
            f"❌ Falló el guardado del canal actual: `{type(exc).__name__}`.",
            ephemeral=True,
        )
        return

    if not persisted:
        await interaction.followup.send(
            f"❌ La DB no conservó el canal. Intenté `{channel.id}` y devolvió `{saved_id}`.",
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
            f"❌ El bot no puede publicar en {channel.mention}.\n"
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
            "Este canal quedó guardado y verificado como destino público. "
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
                "Este canal quedó guardado y verificado como destino público. "
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

    await interaction.followup.send(
        f"✅ **Prueba enviada a {channel.mention}.**\n"
        f"Canal anterior en DB: `{previous_id or 'ninguno'}` • "
        f"Canal guardado ahora: `{saved_id}` • Envío: **{mode}** • "
        f"Backfill: **{recovered}** • Mensaje: `{getattr(test_message, 'id', '—')}`",
        ephemeral=True,
    )


def _register_explicit_channel_commands(runtime, bot):
    registered = []

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
            description="Vincula este canal, lo prueba y recupera rumores pendientes",
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
