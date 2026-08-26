"""Repair publication submits on guild-isolated SQLite databases.

Older guild DB files can predate publication/loan schema migrations because the
base init_db() runs before guild isolation is installed. A transfer modal then
opens normally but INSERT can fail on submit when columns such as operation_type
or season_id are missing.

Run the normal core migration inside the interaction's guild context immediately
before every publication submit, then apply the publication loan columns too.
This is idempotent and does not reset market state or existing data.
"""

from __future__ import annotations

import traceback

import discord

import guild_isolation_patch as guild_isolation
import publication_loan_options_patch as publication_types


async def _report_submit_error(interaction: discord.Interaction, player_name: str, exc: Exception):
    print(
        f"ERROR AJPA publicando {player_name}: {type(exc).__name__}: {exc}\n"
        + traceback.format_exc()
    )
    message = (
        "⚠️ No pude completar la publicación. El bot reparó la base de este servidor; "
        "probá enviar la publicación una vez más."
    )
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception as response_exc:
        print(f"ERROR AJPA informando fallo de publicación: {response_exc}")


def apply_publication_submit_guild_schema_patch(runtime, bot):
    if getattr(runtime, "_ajpa_publication_submit_guild_schema_patch", False):
        return

    FixedModal = publication_types.FixedTypePublicationModal
    LoanModal = publication_types.LoanPublicationModal

    original_fixed_submit = FixedModal.on_submit
    original_loan_submit = LoanModal.on_submit

    def ensure_current_guild_schema():
        # runtime.init_db resolves runtime.db dynamically. After guild isolation,
        # that means the current Discord server's SQLite file, not the legacy DB.
        runtime.init_db()
        publication_types.ensure_schema()

    async def fixed_submit(self, interaction: discord.Interaction):
        try:
            ensure_current_guild_schema()
            await original_fixed_submit(self, interaction)
        except Exception as exc:
            await _report_submit_error(interaction, getattr(self, "jugador", "jugador"), exc)

    async def loan_submit(self, interaction: discord.Interaction):
        try:
            ensure_current_guild_schema()
            await original_loan_submit(self, interaction)
        except Exception as exc:
            await _report_submit_error(interaction, getattr(self, "jugador", "jugador"), exc)

    FixedModal.on_submit = fixed_submit
    LoanModal.on_submit = loan_submit

    runtime._ajpa_publication_submit_guild_schema_patch = True
    print("AJPA publicación: migración per-guild asegurada antes de cada submit")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_publication_schema(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_publication_submit_guild_schema_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_publication_submit_schema_wrapped",
    False,
):
    _apply_guild_isolation_then_publication_schema._ajpa_publication_submit_schema_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_publication_schema
