"""Selector explícito para vincular el canal público del mercado sin tocar Staff.

Agrega /canal_publico_mercado con un parámetro de canal seleccionable. Puede
usarse desde cualquier canal del servidor y guarda el destino elegido en la
misma configuración que consumen rumores, fichajes, préstamos y clausulazos.
"""

from __future__ import annotations

import discord

import public_market_summary_patch as public_summary


_ORIGINAL_APPLY = public_summary.apply_public_market_summary_patch


def _register_explicit_channel_command(runtime, bot):
    if bot.tree.get_command("canal_publico_mercado") is not None:
        return False

    @bot.tree.command(
        name="canal_publico_mercado",
        description="Elegí el canal público donde se anunciará el mercado",
    )
    async def canal_publico_mercado(
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ):
        if not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        if interaction.guild is None:
            await interaction.response.send_message(
                "⚠️ Este comando solo funciona dentro de un servidor.",
                ephemeral=True,
            )
            return
        if canal.guild.id != interaction.guild.id:
            await interaction.response.send_message(
                "⚠️ Elegí un canal de este mismo servidor.",
                ephemeral=True,
            )
            return

        me = interaction.guild.me
        if me is not None:
            perms = canal.permissions_for(me)
            if not perms.view_channel or not perms.send_messages:
                await interaction.response.send_message(
                    f"⚠️ No puedo publicar en {canal.mention}. Dame **Ver canal** y **Enviar mensajes**.",
                    ephemeral=True,
                )
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

    return True


def apply_with_explicit_selector(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    registered = _register_explicit_channel_command(runtime, bot)
    if registered:
        print("AJAP canal público: selector /canal_publico_mercado activo")


if not getattr(public_summary, "_ajap_explicit_public_channel_selector", False):
    public_summary.apply_public_market_summary_patch = apply_with_explicit_selector
    public_summary._ajap_explicit_public_channel_selector = True
