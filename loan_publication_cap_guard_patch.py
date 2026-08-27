"""Final 10% ceiling guard for loan publications.

publication_submit_guild_schema_patch replaces LoanPublicationModal.on_submit to
acknowledge Discord quickly and write directly to the guild database. That
replacement bypassed the earlier validation installed by loan_canon_cap_patch.

This patch wraps the FINAL submit installed by the per-guild publication layer,
so a loan publication can never be persisted above the AJAP 10% per-season cap.
"""

from __future__ import annotations

import discord

import loan_canon_cap_patch as loan_cap
import publication_loan_options_patch as publication_types
import publication_submit_guild_schema_patch as publication_submit


def _install_final_guard(runtime):
    modal = publication_types.LoanPublicationModal
    if getattr(modal, "_ajap_final_loan_publication_cap_guard", False):
        return False

    original_submit = modal.on_submit

    async def guarded_submit(self, interaction: discord.Interaction):
        player = runtime.jugador_por_nombre(self.jugador)
        raw_amount = runtime.price_number(self.precio.value)

        if raw_amount is None:
            await interaction.response.send_message(
                "⚠️ El cargo por temporada debe ser un número.",
                ephemeral=True,
            )
            return

        if player:
            error = loan_cap._validate(player, int(raw_amount))
            if error:
                await interaction.response.send_message(error, ephemeral=True)
                return

        # Solo si pasa el tope se ejecuta el submit final, que hace ACK inmediato,
        # valida el resto de términos y recién entonces escribe la publicación.
        await original_submit(self, interaction)

    modal.on_submit = guarded_submit
    modal._ajap_final_loan_publication_cap_guard = True
    return True


_original_apply_publication_submit = publication_submit.apply_publication_submit_guild_schema_patch


def _apply_publication_submit_with_cap(runtime, bot):
    result = _original_apply_publication_submit(runtime, bot)
    installed = _install_final_guard(runtime)
    if installed:
        print("AJAP préstamo publicación: tope 10% validado en submit final per-guild")
    return result


if not getattr(
    publication_submit.apply_publication_submit_guild_schema_patch,
    "_ajap_final_loan_publication_cap_wrapped",
    False,
):
    _apply_publication_submit_with_cap._ajap_final_loan_publication_cap_wrapped = True
    publication_submit.apply_publication_submit_guild_schema_patch = _apply_publication_submit_with_cap
