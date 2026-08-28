"""Admin command to publish AJPA's bot introduction in the current channel."""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import market_usage_channel_patch as market_channels


APP = None
BOT = None

# This is an administrative utility and must work outside the market-only channel.
market_channels.EXEMPT_COMMANDS.add("presentacion_bot")

INTRO_MESSAGE = """👋⚽ **¡Bienvenidos a la Asociación de Jugadores de PES Argentina!**

Soy **AJPA Transfer Market**, el sistema que van a usar para gestionar sus clubes durante la competencia.

Conmigo van a poder gestionar todo lo relacionado con su club:

💰 Presupuesto
🔄 Fichajes y ventas
🤝 Negociaciones
📤 Préstamos
🔁 Intercambios
🚨 Clausulazos
🆓 Jugadores libres
📋 Planteles y movimientos del mercado

Mi objetivo es que puedan hacer todo de la forma más simple y automática posible, sin depender de anotaciones manuales.

Todavía estoy en constante mejora, así que si durante el uso encuentran **algún error, comportamiento raro o bug**, no duden en avisarle al **Staff de AJPA**. Cada reporte nos ayuda a mejorar el sistema para todos.

Y si tienen alguna duda sobre cómo usar alguna función, también pueden consultar al Staff.

👔 Ustedes manejan el club.
⚽ Ustedes juegan los partidos.
🤖 **Yo me encargo del mercado.**

¡Éxitos a todos y que tengan un gran mercado de pases! 🇦🇷🔥"""


def apply_bot_intro_message_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajpa_bot_intro_message_patch", False):
        return

    if bot.tree.get_command("presentacion_bot") is None:

        @bot.tree.command(
            name="presentacion_bot",
            description="Publica la presentación de AJPA Transfer Market en este canal",
        )
        async def presentacion_bot(interaction: discord.Interaction):
            if not APP.es_admin(interaction):
                await interaction.response.send_message(
                    "⛔ Solo el Staff puede publicar la presentación del bot.",
                    ephemeral=True,
                )
                return

            channel = getattr(interaction, "channel", None)
            if channel is None or not hasattr(channel, "send"):
                await interaction.response.send_message(
                    "⚠️ No pude identificar el canal donde ejecutaste el comando.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True, thinking=True)

            try:
                await channel.send(
                    INTRO_MESSAGE,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "⛔ No tengo permiso para enviar mensajes en este canal.",
                    ephemeral=True,
                )
                return
            except discord.HTTPException as exc:
                await interaction.followup.send(
                    "⚠️ Discord no me dejó publicar el mensaje en este canal. "
                    f"Error: {type(exc).__name__}.",
                    ephemeral=True,
                )
                return

            mention = getattr(channel, "mention", "este canal")
            await interaction.followup.send(
                f"✅ Presentación enviada en {mention}.",
                ephemeral=True,
            )

    runtime._ajpa_bot_intro_message_patch = True
    print("AJPA presentación del bot activa: /presentacion_bot publica en el canal actual")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_intro(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_bot_intro_message_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_bot_intro_message_wrapped",
    False,
):
    _apply_guild_isolation_then_intro._ajpa_bot_intro_message_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_intro
