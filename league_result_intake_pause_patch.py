"""AJAP Liga result-intake resume switch.

This module used to be the emergency hard pause. Staff has now finished the
manual checkpoint through the four verified matches received while intake was
disabled, so startup must leave the normal result pipeline active again.

It still loads the strict PES6 scoreboard reader v2 and the one-time 60-match
checkpoint before Discord connects. It intentionally does NOT replace
``league.handle`` or any late-bound feedback/evidence/rescue handler.
"""
from __future__ import annotations

# Final local-score parser: only accepts a structurally proved PES6 score panel.
import league_scoreboard_reader_v2_patch  # noqa: F401

# One-time additive backfill for the four Staff-verified matches sent during the
# pause. The patch is idempotent and refreshes the shared Discord/mobile DB view.
import league_post_pause_checkpoint_60_patch  # noqa: F401

print(
    "AJAP Liga: RESULTADOS REACTIVADOS; checkpoint 60 armado + "
    "lector PES6 v2 activo"
)
