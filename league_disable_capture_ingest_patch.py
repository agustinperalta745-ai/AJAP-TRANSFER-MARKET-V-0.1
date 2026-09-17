"""Disable the legacy AJPA screenshot result-ingestion path.

Official league results are now maintained in GES and synchronized through the
staff action "GES actualizada".  The old Discord screenshot readers must not run
or consume OCR/vision resources, but the league database/helpers remain available
for standings, Staff corrections and the app.
"""
from __future__ import annotations

import guild_isolation_patch as guild_isolation
import league_automation_patch as league


async def _ges_only_message_handler(runtime, bot, message):
    """Intentionally ignore Discord attachments/text as official result input."""
    return


def _disable_capture_ingest(runtime):
    league.handle = _ges_only_message_handler
    runtime._ajap_capture_reader_disabled = True
    print("AJPA Liga: lector de capturas desactivado; resultados oficiales vía GES")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_disable_capture_reader(runtime, bot):
    # Let the existing league/admin patches initialize first, then force the final
    # message handler to the GES-only no-op so no later wrapper can revive OCR.
    _original_apply_guild_isolation_patch(runtime, bot)
    _disable_capture_ingest(runtime)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_capture_reader_disabled_wrapped",
    False,
):
    _apply_guild_isolation_then_disable_capture_reader._ajap_capture_reader_disabled_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_disable_capture_reader
