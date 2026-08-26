"""Compatibility fix for Discord modal submits under guild isolation.

The project allows discord.py >=2.4,<3. In newer 2.x releases Modal._scheduled_task
receives an additional `resolved` argument. guild_isolation_patch originally
wrapped the private method with the older `(self, interaction, components)`
signature, so Discord raised TypeError BEFORE any modal on_submit callback ran.
That produced the client-side generic "Algo ha fallado" on every server and also
meant our publication-level error handling could never execute.

This module is imported before run_bot calls apply_guild_isolation_patch. It saves
the library's real modal task, lets the complete guild-isolation wrapper chain
install normally, and then replaces only the modal task with a version-tolerant
wrapper that preserves the per-guild ContextVar and forwards every extra argument.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation


# At import time guild isolation has not been applied yet, so this is discord.py's
# real implementation (whatever supported 2.x version Railway installed).
_BASE_MODAL_SCHEDULED_TASK = discord.ui.Modal._scheduled_task
_ORIGINAL_APPLY_GUILD_ISOLATION = guild_isolation.apply_guild_isolation_patch


def _install_modal_compat():
    current = discord.ui.Modal._scheduled_task
    if getattr(current, "_ajpa_modal_signature_compat", False):
        return

    async def guild_modal_task_compat(self, interaction, components, *extra):
        token = guild_isolation._CURRENT_GUILD_ID.set(
            guild_isolation._interaction_guild_id(interaction)
        )
        try:
            # discord.py 2.4/2.5 passes no extra args; newer 2.x passes resolved.
            return await _BASE_MODAL_SCHEDULED_TASK(
                self,
                interaction,
                components,
                *extra,
            )
        finally:
            guild_isolation._CURRENT_GUILD_ID.reset(token)

    guild_modal_task_compat._ajap_guild_context = True
    guild_modal_task_compat._ajpa_modal_signature_compat = True
    discord.ui.Modal._scheduled_task = guild_modal_task_compat
    print("AJPA Discord modal compat: firma 2.x flexible + contexto guild activo")


def _apply_guild_isolation_then_modal_compat(runtime, bot):
    _ORIGINAL_APPLY_GUILD_ISOLATION(runtime, bot)
    _install_modal_compat()


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_modal_signature_compat_wrapper",
    False,
):
    _apply_guild_isolation_then_modal_compat._ajpa_modal_signature_compat_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_modal_compat
