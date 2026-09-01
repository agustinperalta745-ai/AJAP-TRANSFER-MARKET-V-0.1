"""Discord command that securely pairs AJPA Mobile with the current manager."""

from __future__ import annotations

import discord

# Final Discord-facing brand guard. Historical modules may still contain the
# old AJAP typo internally, but users must always see the canonical AJPA name.
import brand_identity_patch  # noqa: F401
import mobile_write_api
import classic_rival_discord_patch
import classic_rival_myclub_button_patch


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

            # Critical: the code must be created in the exact same SQLite file
            # that /api/v1/auth/pair reads. Using runtime.db here depends on the
            # Discord guild ContextVar and can write the code to a different
            # guild DB than AJPA Mobile is configured to consume. That makes a
            # brand-new code look "inexistente, vencido o ya usado" immediately.
            code = mobile_write_api.issue_pair_code(
                mobile_write_api.write_db,
                int(interaction.user.id),
                is_staff=is_staff,
            )

            # Keep this informational field based on the Discord guild where the
            # manager executed the command; it does not affect pairing storage.
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

    # Mounted after guild isolation and after bot.py imported the final MI CLUB
    # Treasury layer. This keeps Discord and Mobile on the same classic tables and
    # puts the button on the exact dashboard managers actually see.
    classic_rival_discord_patch.apply_classic_rival_discord_patch(runtime, bot)
    classic_rival_myclub_button_patch.apply_classic_rival_myclub_button_patch(runtime, bot)

    bot._ajpa_mobile_pairing_patch = True
    print("AJPA Mobile: /app_codigo habilitado • clásico rival visible en MI CLUB y Discord")