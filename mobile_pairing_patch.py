"""Discord command and main-menu button for securely pairing AJPA Mobile."""

from __future__ import annotations

import discord

# Final Discord-facing brand guard. Historical modules may still contain the
# old AJAP typo internally, but users must always see the canonical AJPA name.
import brand_identity_patch  # noqa: F401
import mobile_write_api
import classic_rival_discord_patch
import classic_rival_myclub_button_patch
import classic_rival_ownership_reset_patch
import ges_authoritative_snapshot_patch
import ges_new_result_cards_patch
import mobile_manager_names_patch
import my_club_menu_patch as my_club


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
                "Generá el código dentro del servidor de AJPA.", ephemeral=True
            )
            return
        try:
            is_staff = bool(
                isinstance(interaction.user, discord.Member)
                and interaction.user.guild_permissions.administrator
            )

            club = runtime.club_de(interaction.user.id)
            if not is_staff and not club:
                await interaction.response.send_message(
                    "⚠️ Necesitás tener un club asignado para vincular AJPA Mobile.",
                    ephemeral=True,
                )
                return

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

    # Instala la misma limpieza/validación antes de montar la interfaz Discord.
    # Es idempotente: si el proceso Mobile ya la aplicó, no vuelve a tocar nada.
    classic_rival_ownership_reset_patch.apply_classic_rival_ownership_reset_patch()

    # Mounted after guild isolation and after bot.py imported the final MI CLUB
    # Treasury layer. This keeps Discord and Mobile on the same classic tables and
    # puts the button on the exact dashboard managers actually see.
    classic_rival_discord_patch.apply_classic_rival_discord_patch(runtime, bot)
    classic_rival_myclub_button_patch.apply_classic_rival_myclub_button_patch(runtime, bot)

    # GES is the absolute source of truth for the active competition. Mount this
    # after the Mobile/league patch chain so its snapshot reader is the final one.
    ges_authoritative_snapshot_patch.apply_authoritative_ges_snapshot(runtime, bot)
    # Manager names decorate the final GES standings, so they must mount after
    # the authoritative snapshot reader instead of duplicating standings logic.
    mobile_manager_names_patch.apply_mobile_manager_names_patch(runtime, bot)
    # After the authoritative reader is installed, detect fixtures that were not
    # present before this sync and publish only those with the existing result card.
    ges_new_result_cards_patch.apply_ges_new_result_cards(runtime, bot)

    # Extend the main menu shown before entering MI CLUB.
    base_view = runtime.MercadoView

    class MobilePairingMarketView(base_view):
        def __init__(self):
            super().__init__()
            button = discord.ui.Button(
                label="Vincular con la app",
                emoji="📱",
                style=discord.ButtonStyle.primary,
                custom_id="ajpa_main_app_codigo",
                row=3,
            )
            button.callback = self._generate_pair_code
            self.add_item(button)

        async def _generate_pair_code(self, interaction: discord.Interaction):
            token = my_club._guild_context(interaction)
            try:
                # Share the command's storage, expiry and private response.
                await app_codigo.callback(interaction)
            finally:
                my_club._reset_guild_context(token)

    MobilePairingMarketView.__name__ = "MercadoView"
    runtime.MercadoView = MobilePairingMarketView

    bot._ajpa_mobile_pairing_patch = True
    print("AJPA Mobile: /app_codigo y botón Vincular con la app habilitados en el menú principal")
