"""Clear first-step explanation for the manual V1 reset."""

from __future__ import annotations

import discord

import admin_manual_reset_patch as manual_reset


_original_reset_warning_embed = manual_reset._reset_warning_embed


def _reset_warning_embed(final=False):
    if final:
        return _original_reset_warning_embed(final=True)

    embed = discord.Embed(
        title="🚨 RESET V1 • ANTES DE CONTINUAR",
        description=(
            "**Todavía no se reseteó nada.** Esta pantalla solo te explica qué va a pasar "
            "si continuás y después confirmás el reseteo."
        ),
        color=discord.Color.orange(),
    )
    embed.add_field(
        name="🔄 Jugadores y planteles",
        value=(
            "Cada jugador volverá al **club de origen indicado en su JSON**. "
            "Las transferencias, préstamos, clausulazos y liberaciones realizadas después "
            "de esa base dejarán de formar parte del estado actual."
        ),
        inline=False,
    )
    embed.add_field(
        name="🧹 Datos de mercado que se limpiarán",
        value=(
            "• Publicaciones activas y antiguas\n"
            "• Ofertas y contraofertas\n"
            "• Operaciones y transferencias\n"
            "• Historial de pases de mercado\n"
            "• Préstamos y cánones asociados\n"
            "• Clausulazos\n"
            "• Liberaciones registradas\n"
            "• Ventanas/historial de mercado"
        ),
        inline=False,
    )
    embed.add_field(
        name="💰 Economía",
        value=(
            "Los movimientos económicos auditados que pertenecen a esas operaciones "
            "de mercado se revertirán para no dejar saldos alterados por datos que fueron borrados."
        ),
        inline=False,
    )
    embed.add_field(
        name="✅ Lo que se conserva",
        value=(
            "• DT asignados a sus equipos\n"
            "• Equipos y archivos JSON cargados\n"
            "• Escudos/emojis\n"
            "• Canales configurados\n"
            "• Configuración general del bot"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔒 Estado después del reset",
        value=(
            "El mercado quedará **CERRADO** y el servidor quedará listo para comenzar "
            "nuevamente desde la base de planteles definida por los JSON."
        ),
        inline=False,
    )
    embed.add_field(
        name="⚠️ Importante",
        value=(
            "Apretar **CONTINUAR** todavía **NO ejecuta el reset**. "
            "Después vas a ver una **última confirmación** con el botón `SÍ, RESETEAR AHORA`."
        ),
        inline=False,
    )
    embed.set_footer(text="Podés cancelar ahora o en la siguiente pantalla")
    return embed


manual_reset._reset_warning_embed = _reset_warning_embed
print("AJAP reset manual: explicación detallada antes de la confirmación final")
