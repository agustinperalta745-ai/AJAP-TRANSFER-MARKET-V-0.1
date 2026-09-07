"""Keep per-competition GES sync final when older snapshot/card layers initialize.

Some mobile pairing code lazily installs the authoritative snapshot and result
card wrappers on the first /app_codigo use. The old snapshot installer replaces
ges.sync_from_ges. This shim lets it install its Mobile reader, then restores the
season-aware authoritative sync before the result-card layer wraps it.
"""

import ges_authoritative_snapshot_patch as authoritative
import league_ges_manual_sync_patch as ges
import season_ges_authority_patch as seasonal
from season_ges_snapshot_cleanup_patch import apply_season_snapshot_cleanup

_BASE_APPLY = authoritative.apply_authoritative_ges_snapshot


def _apply_with_seasonal_final(runtime, bot):
    # If result cards already wrap the season-aware sync, the authoritative
    # installer is already initialized and returns immediately. Preserve that
    # wrapper instead of stripping it on every later /app_codigo invocation.
    had_result_cards = bool(getattr(ges.sync_from_ges, "_ajpa_new_result_cards", False))
    _BASE_APPLY(runtime, bot)
    if had_result_cards:
        return
    seasonal.apply_season_ges_authority(runtime, bot)
    apply_season_snapshot_cleanup(runtime, bot)


authoritative.apply_authoritative_ges_snapshot = _apply_with_seasonal_final
print("AJPA GES: sincronización por temporada fijada como capa final")
