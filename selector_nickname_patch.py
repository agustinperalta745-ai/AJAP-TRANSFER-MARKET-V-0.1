"""Final nickname hook for the /mercado team selector.

This installs after guild isolation and all late AJAP patches, so whichever
TeamSelect class is actually live in /mercado gets wrapped. After a successful
club choice, the member nickname is forced to ``Nombre | Equipo``.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import member_nickname_patch as nicknames
import team_assignment as teams


def _install_final_selector_hook():
    SelectClass = teams.TeamSelect
    original = SelectClass.callback

    if getattr(original, "_ajap_final_selector_nickname", False):
        return

    async def callback(self, interaction: discord.Interaction):
        await original(self, interaction)

        # Only apply the suffix if the selector actually completed an assignment.
        team = teams.club_de(interaction.user.id)
        if not team:
            return

        changed = await nicknames._apply_club_nickname(interaction, team)
        if changed:
            print(
                f"AJAP selector nickname OK: guild={getattr(interaction.guild, 'id', None)} "
                f"user={interaction.user.id} club={team}"
            )
            return

        print(
            f"WARNING AJAP selector nickname failed: guild={getattr(interaction.guild, 'id', None)} "
            f"user={interaction.user.id} club={team}"
        )
        try:
            await interaction.followup.send(
                "⚠️ El club quedó asignado, pero Discord no me permitió cambiar tu apodo. "
                "El bot necesita **Administrar apodos**, su rol debe estar por encima del tuyo "
                "y no puede cambiar el apodo del propietario del servidor.",
                ephemeral=True,
            )
        except discord.HTTPException:
            pass

    callback._ajap_final_selector_nickname = True
    SelectClass.callback = callback
    print("AJAP: selector final /mercado => apodo Nombre | Equipo activo")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


async_marker = False


def _apply_guild_isolation_then_selector(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    _install_final_selector_hook()


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_selector_nickname_wrapped",
    False,
):
    _apply_guild_isolation_then_selector._ajap_selector_nickname_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_selector
