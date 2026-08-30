"""Discord command that securely pairs AJPA Mobile with the current manager."""

from __future__ import annotations

import discord

import mobile_write_api


def apply_mobile_pairing_patch(runtime, bot) -> None:
    if getattr(bot, "_ajpa_mobile_pairing_patch", False):
        return

    @bot.tree.command(
        name="app_codigo",
        description="Genera un código para vincular tu cuenta de Discord con AJPA Mobile",
    )
    async def app_codigo(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(
                "Usá este comando dentro del servidor de AJPA.", ephemeral=True
            )
            return
        try:
            is_staff = bool(
                isinstance(interaction.user, discord.Member)
                and interaction.user.guild_permissions.administrator
            )
            code = mobile_write_api.issue_pair_code(
                runtime.db,
                int(interaction.user.id),
                is_staff=is_staff,
            )
            club = runtime.club_de(interaction.user.id)
            embed = discord.Embed(
                title="📱 Vincular AJPA Mobile",
                description=(
                    "Abrí **Perfil → Vincular Discord** en la app e ingresá este código:\n\n"
                    f"## `{code}`\n\n"
                    "⏱️ Vence en **10 minutos** y se puede usar una sola vez."
                ),
            )
            embed.add_field(
                name="Cuenta",
                value=f"{interaction.user.mention}\nClub: **{club or 'Staff / sin club'}**",
                inline=False,
            )
            embed.set_footer(text="No compartas este código con otra persona")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as exc:
            print(f"AJPA mobile pairing error: {type(exc).__name__}: {exc}")
            await interaction.response.send_message(
                "⚠️ No pude generar el código de la app. Intentá nuevamente.",
                ephemeral=True,
            )

    bot._ajpa_mobile_pairing_patch = True
    print("AJPA Mobile: /app_codigo habilitado")
