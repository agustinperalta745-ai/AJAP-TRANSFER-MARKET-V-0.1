"""Manual, double-confirmed V1 reset inside Administration -> Gestion."""

from __future__ import annotations

import discord

import staff_admin_organized_patch as staff_admin
import v1_official_reset_patch as v1_reset


def _app():
    return staff_admin.APP


def _reset_warning_embed(final=False):
    if final:
        embed = discord.Embed(
            title="⛔ ÚLTIMA CONFIRMACIÓN • RESET V1",
            description=(
                "Estás a un clic de resetear los datos de mercado de **este servidor**.\n\n"
                "Esta acción no se puede deshacer desde el bot."
            ),
            color=discord.Color.red(),
        )
        embed.add_field(
            name="Se va a resetear",
            value=(
                "• Jugadores al club original de sus JSON\n"
                "• Publicaciones, ofertas y operaciones\n"
                "• Historial de pases, préstamos y clausulazos\n"
                "• Liberaciones de jugadores de la prueba\n"
                "• Ventanas de mercado y mercado a CERRADO"
            ),
            inline=False,
        )
        embed.add_field(
            name="Se conserva",
            value="• DT asignados\n• Canales configurados\n• Equipos/JSON\n• Configuración general",
            inline=False,
        )
        embed.set_footer(text="Solo un administrador puede ejecutar el reset")
        return embed

    embed = discord.Embed(
        title="🚨 RESET V1 • ESTE SERVIDOR",
        description=(
            "Herramienta de mantenimiento para volver la liga a su base limpia.\n"
            "**No reinicia Discord ni borra los equipos cargados.**"
        ),
        color=discord.Color.orange(),
    )
    embed.add_field(
        name="Qué hace",
        value=(
            "Restaura cada jugador a su club de origen según los JSON y limpia la actividad "
            "de mercado del servidor. También revierte los efectos económicos auditados de "
            "préstamos, clausulazos y liberaciones que se estén eliminando."
        ),
        inline=False,
    )
    embed.add_field(
        name="Qué NO toca",
        value="DT asignados, canales configurados, equipos cargados y configuración del bot.",
        inline=False,
    )
    embed.set_footer(text="Hay una segunda confirmación antes de ejecutar")
    return embed


class ResetCancelButton(discord.ui.Button):
    def __init__(self, row=0):
        super().__init__(
            label="CANCELAR",
            emoji="✖️",
            style=discord.ButtonStyle.secondary,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        app = _app()
        if not app or not app.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[staff_admin.section_embed(
                "⚙️ GESTIÓN",
                "Configuración general del torneo y del mercado.",
                ["👥 Asignaciones", "🗓️ Cambiar temporada", "📤 Exportar mercado", "🚨 Reset V1"],
            )],
            view=staff_admin.ManagementView(),
        )


class ResetFinalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=90)

        confirm = discord.ui.Button(
            label="SÍ, RESETEAR AHORA",
            emoji="🚨",
            style=discord.ButtonStyle.danger,
            row=0,
        )
        confirm.callback = self._confirm
        self.add_item(confirm)
        self.add_item(ResetCancelButton(row=0))

    async def _confirm(self, interaction: discord.Interaction):
        app = _app()
        if not app or not app.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        if not interaction.guild_id:
            await interaction.response.send_message(
                "⚠️ El reset solo se puede ejecutar dentro de un servidor.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            applied, stats = v1_reset.manual_reset_current_guild(
                app,
                int(interaction.guild_id),
                int(interaction.user.id),
            )
        except Exception as exc:
            embed = discord.Embed(
                title="❌ RESET V1 FALLÓ",
                description=(
                    "No se completó el reset. Revisá los logs antes de volver a intentarlo.\n\n"
                    f"`{type(exc).__name__}: {str(exc)[:700]}`"
                ),
                color=discord.Color.red(),
            )
            await interaction.edit_original_response(
                content=None,
                embeds=[embed],
                view=staff_admin.BackAdminOnlyView(),
            )
            return

        embed = discord.Embed(
            title="✅ RESET V1 COMPLETADO",
            description="La base de este servidor volvió al estado limpio definido por los JSON.",
            color=discord.Color.green(),
        )
        embed.add_field(name="👥 Jugadores restaurados", value=str(stats.get("players", 0)), inline=True)
        embed.add_field(name="🧹 Tablas limpiadas", value=str(stats.get("tables", 0)), inline=True)
        embed.add_field(name="💰 Saldos revertidos", value=str(stats.get("finances", 0)), inline=True)
        embed.add_field(name="🔒 Mercado", value="CERRADO", inline=True)
        embed.set_footer(text=f"Reset manual ejecutado por {interaction.user.display_name}")
        await interaction.edit_original_response(
            content=None,
            embeds=[embed],
            view=staff_admin.BackAdminOnlyView(),
        )


class ResetFirstConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

        proceed = discord.ui.Button(
            label="CONTINUAR",
            emoji="⚠️",
            style=discord.ButtonStyle.danger,
            row=0,
        )
        proceed.callback = self._proceed
        self.add_item(proceed)
        self.add_item(ResetCancelButton(row=0))

    async def _proceed(self, interaction: discord.Interaction):
        app = _app()
        if not app or not app.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[_reset_warning_embed(final=True)],
            view=ResetFinalView(),
        )


class ManualResetButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="RESET V1",
            emoji="🚨",
            style=discord.ButtonStyle.danger,
            row=row,
            custom_id="ajap_admin_manual_v1_reset",
        )

    async def callback(self, interaction: discord.Interaction):
        app = _app()
        if not app or not app.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        if not interaction.guild_id:
            await interaction.response.send_message(
                "⚠️ El reset solo se puede ejecutar dentro de un servidor.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[_reset_warning_embed(final=False)],
            view=ResetFirstConfirmView(),
        )


_ORIGINAL_MANAGEMENT_VIEW = staff_admin.ManagementView
_ORIGINAL_SECTION_EMBED = staff_admin.section_embed


class ManagementViewWithReset(_ORIGINAL_MANAGEMENT_VIEW):
    def __init__(self):
        super().__init__()
        self.add_item(ManualResetButton(row=1))


ManagementViewWithReset.__name__ = "ManagementView"
staff_admin.ManagementView = ManagementViewWithReset


def _section_embed_with_reset(title, description, tools):
    tools = list(tools)
    if "GESTIÓN" in str(title).upper() and not any("reset" in str(item).casefold() for item in tools):
        tools.append("🚨 Reset V1")
    return _ORIGINAL_SECTION_EMBED(title, description, tools)


staff_admin.section_embed = _section_embed_with_reset
print("AJAP reset manual activo: Administración > Gestión > RESET V1 con doble confirmación")
