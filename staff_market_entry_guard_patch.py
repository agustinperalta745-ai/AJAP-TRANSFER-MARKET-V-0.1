"""Final /mercado entry guard for AJAP Staff.

An administrator may enter Perfil Usuario and even keep a club assignment for
real-world testing. That state must never decide what a *new* /mercado command
opens. Every fresh admin invocation starts at Staff; only navigation inside that
specific panel may enter user/admin profile mode.

This module is intentionally imported last in bot.py and wraps the final guild
isolation installer, so no later UI patch can re-register an older /mercado
callback over this rule.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import staff_dashboard_patch as staff_dashboard
import staff_profile_gate_patch as profiles


APP = None
BOT = None


def apply_staff_market_entry_guard(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajap_staff_market_entry_guard", False):
        return

    current_command = bot.tree.get_command("mercado")
    prior_callback = getattr(current_command, "callback", None)

    async def guarded_mercado(interaction: discord.Interaction):
        # Critical invariant: a NEW slash command from Staff always starts at
        # Staff, regardless of a club selected/assigned during earlier testing.
        if runtime.es_admin(interaction):
            profiles.APP = runtime
            profiles.BOT = bot
            profiles._set_mode(interaction, "staff")
            await interaction.response.send_message(
                embed=staff_dashboard.staff_dashboard_embed(),
                view=profiles.StaffProfileChoiceView(),
                ephemeral=True,
            )
            return

        # Normal users keep the exact final callback produced by the rest of the
        # patch stack (team selector, channel restrictions, manager panel, etc.).
        if callable(prior_callback):
            await prior_callback(interaction)
            return

        # Defensive fallback: this should never be needed, but avoids exposing
        # Staff UI to a normal user if another startup change removes /mercado.
        if not runtime.club_de(interaction.user.id):
            import team_assignment as teams

            await interaction.response.send_message(
                embed=teams.welcome_embed(),
                view=teams.TeamChoiceView(),
                ephemeral=True,
            )
            return

        import manager_menu_patch as manager

        await interaction.response.send_message(
            embed=manager.manager_panel_embed(interaction.user.id),
            view=manager.market_view_for(interaction),
            ephemeral=True,
        )

    bot.tree.remove_command("mercado")
    bot.tree.command(
        name="mercado",
        description="Abre el panel principal de AJAP Transfer Market",
    )(guarded_mercado)

    runtime._ajap_staff_market_entry_guard = True
    print(
        "AJAP Staff entry guard activo: cada nuevo /mercado de admin inicia en Staff"
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_staff_entry_guard(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_staff_market_entry_guard(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_staff_market_entry_guard_wrapped",
    False,
):
    _apply_guild_isolation_then_staff_entry_guard._ajap_staff_market_entry_guard_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_staff_entry_guard

# PSG.json existe en data/, pero además necesita sembrar roster_players y
# league_teams para que el selector JSON-only pueda mostrarlo. Se importa acá,
# después del guard Staff, para que su wrapper quede en la cadena final antes
# de que run_bot capture y ejecute apply_guild_isolation_patch.
import psg_roster_patch  # noqa: F401,E402
