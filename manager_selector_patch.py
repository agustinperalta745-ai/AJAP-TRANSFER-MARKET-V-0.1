"""Make the first menu shown after club selection use the final manager panel."""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation


APP = None


def _install_selector_manager_hook():
    import team_assignment as teams

    select_cls = teams.TeamSelect
    original = select_cls.callback
    if getattr(original, "_ajap_manager_selector", False):
        return

    async def callback(self, interaction: discord.Interaction):
        await original(self, interaction)

        club = APP.club_de(interaction.user.id)
        if not club:
            return

        # The selector already completed the assignment (and the nickname hook,
        # when available). Replace only the success screen with the final menu.
        try:
            await interaction.edit_original_response(
                content=None,
                embed=APP.panel_embed(interaction.user.id),
                view=APP.manager_market_view_for(interaction),
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    callback._ajap_manager_selector = True
    select_cls.callback = callback
    print("AJAP selector => panel manager filtrado activo")


def apply_manager_selector_patch(runtime, bot):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_manager_selector_patch", False):
        return
    _install_selector_manager_hook()
    runtime._ajap_manager_selector_patch = True


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_manager_selector(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_manager_selector_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_manager_selector_wrapped",
    False,
):
    _apply_guild_isolation_then_manager_selector._ajap_manager_selector_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_manager_selector
