"""Formas explícitas de vincular el canal público del mercado sin tocar Staff.

- /canal_publico_mercado vincula directamente el canal donde se ejecuta.
- /vincular_resumen_mercado queda como alias por compatibilidad.

Ambos guardan el destino en la misma configuración usada por rumores,
transferencias, préstamos, intercambios, clausulazos y opciones de compra.
"""

from __future__ import annotations

import discord

import market_usage_channel_patch as market_usage
import public_market_summary_patch as public_summary


# Estos comandos son de CONFIGURACIÓN y justamente deben poder ejecutarse fuera
# del canal único de uso del mercado. Sin esta excepción, /canal_mercado los
# bloquea antes de que puedan vincular #RESUMEN-MERCADO.
market_usage.EXEMPT_COMMANDS.update(
    {
        "canal_publico_mercado",
        "vincular_resumen_mercado",
        "canal_resumen_mercado",
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

    return registered


def apply_with_explicit_selector(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    registered = _register_explicit_channel_commands(runtime, bot)
    if registered:
        print("AJAP canal público: comandos activos " + ", ".join(registered))


if not getattr(public_summary, "_ajap_explicit_public_channel_selector", False):
    public_summary.apply_public_market_summary_patch = apply_with_explicit_selector
    public_summary._ajap_explicit_public_channel_selector = True
