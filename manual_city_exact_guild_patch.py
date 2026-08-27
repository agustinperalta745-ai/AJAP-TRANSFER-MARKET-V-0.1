"""Final exact-guild bridge for Staff -> Perfil Usuario team selection.

The persistent Staff profile buttons can survive deploys, while a module-level
ContextVar may still point at another guild when the next view is constructed.
This layer builds the team selector with interaction.guild explicitly, so the
manual :mancity: emoji always belongs to the same server receiving the component.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import staff_profile_gate_patch as profiles
import staff_admin_organized_patch as admin_tools


class ExactGuildStaffProfileChoiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def on_error(self, interaction, error, item):
        detail = f"{type(error).__name__}: {error}"[:900]
        print(
            "ERROR AJAP perfil exact-guild: "
            f"item={getattr(item, 'custom_id', None)} {detail}"
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"⚠️ No pude abrir ese perfil.\n`{detail}`",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"⚠️ No pude abrir ese perfil.\n`{detail}`",
                    ephemeral=True,
                )
        except Exception:
            pass

    @discord.ui.button(
        label="PERFIL USUARIO",
        emoji="👤",
        style=discord.ButtonStyle.primary,
        row=0,
        custom_id="ajap_staff_profile_user",
    )
    async def user_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        app = profiles.APP
        if app is None or not app.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        if not interaction.response.is_done():
            await interaction.response.defer()
        profiles._set_mode(interaction, "user")

        club = app.club_de(interaction.user.id)
        if not club:
            import team_assignment as teams

            # Critical fix: pass the concrete interaction guild into BOTH the
            # embed and select view. No cache/context lookup is used for :mancity:.
            view = teams.TeamChoiceView(guild=interaction.guild)
            view.add_item(profiles.BackToStaffButton(row=1))
            await profiles._followup_screen(
                interaction,
                embed=teams.welcome_embed(interaction.guild),
                view=view,
            )
            return

        await profiles._followup_screen(
            interaction,
            embed=profiles._normal_user_embed(interaction.user.id),
            view=profiles._user_market_view(interaction),
        )

    @discord.ui.button(
        label="PERFIL ADMINISTRADOR",
        emoji="⚙️",
        style=discord.ButtonStyle.secondary,
        row=0,
        custom_id="ajap_staff_profile_admin",
    )
    async def admin_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        app = profiles.APP
        if app is None or not app.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        if not interaction.response.is_done():
            await interaction.response.defer()
        profiles._set_mode(interaction, "admin")
        await profiles._followup_screen(
            interaction,
            embed=admin_tools.admin_home_embed(),
            view=admin_tools.OrganizedAdminHomeView(),
        )


def _install_exact_profile_view(runtime, bot):
    profiles.APP = runtime
    profiles.BOT = bot
    profiles.StaffProfileChoiceView = ExactGuildStaffProfileChoiceView
    runtime.StaffProfileChoiceView = ExactGuildStaffProfileChoiceView
    try:
        bot.add_view(ExactGuildStaffProfileChoiceView())
    except Exception as exc:
        print(f"WARNING AJAP exact-guild persistent view: {type(exc).__name__}: {exc}")
    print("AJAP Perfil Usuario exact-guild activo: :mancity: resuelto desde interaction.guild")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_exact_profile(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    _install_exact_profile_view(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_exact_guild_profile_wrapped",
    False,
):
    _apply_guild_isolation_then_exact_profile._ajap_exact_guild_profile_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_exact_profile
