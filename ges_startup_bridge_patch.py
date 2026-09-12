"""Restore the official GES layers in the final AJPA runtime startup.

The Panel Maestro already calls the GES config/sync endpoints, but the current
startup stopped installing the manual GES layer and its per-competition authority.
Patch competition-cycle startup before bot.py imports it so GES is installed only
after guild isolation, Liga and the competition schema are all ready.
"""

import competition_cycle
from ges_config_mobile_transport_fix import apply_final_ges_mobile_mutation_tunnel
from league_ges_manual_sync_patch import apply_manual_ges_sync
from season_ges_authority_patch import apply_season_ges_authority


if not getattr(competition_cycle, "_ajpa_ges_startup_bridge_installed", False):
    _BASE_APPLY_COMPETITION_CYCLE = competition_cycle.apply_competition_cycle

    def _apply_cycle_with_ges(runtime, bot):
        _BASE_APPLY_COMPETITION_CYCLE(runtime, bot)
        # Install the authenticated /admin/ges-sync endpoint and capture the
        # running Discord event loop on_ready.
        apply_manual_ges_sync(runtime, bot)
        # Each competition owns its GES links and this replaces sync_from_ges
        # with the season-aware authoritative implementation.
        apply_season_ges_authority(runtime, bot)
        # GES authority installs a late GET /ges-config handler. Re-assert the
        # Android mutation tunnel afterwards so GUARDAR ENLACES reaches POST
        # instead of being mistaken for another GET.
        apply_final_ges_mobile_mutation_tunnel()

    competition_cycle.apply_competition_cycle = _apply_cycle_with_ges
    competition_cycle._ajpa_ges_startup_bridge_installed = True
    print("AJPA startup: GES config + manual sync attached after competition cycle")
