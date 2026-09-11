"""Restore the official GES layers in the final AJPA runtime startup.

The mobile Panel Maestro already calls the GES config/sync endpoints, but the
current deterministic run_bot startup no longer installs the manual GES layer or
the per-competition authority layer. Hook guild isolation before run_bot imports
its function so both layers are installed with the real runtime and Discord bot.
"""

import guild_isolation_patch
from league_ges_manual_sync_patch import apply_manual_ges_sync
from season_ges_authority_patch import apply_season_ges_authority


if not getattr(guild_isolation_patch, "_ajpa_ges_startup_bridge_installed", False):
    _BASE_APPLY_GUILD_ISOLATION = guild_isolation_patch.apply_guild_isolation_patch

    def _apply_with_ges(runtime, bot):
        _BASE_APPLY_GUILD_ISOLATION(runtime, bot)
        # Install the authenticated /admin/ges-sync endpoint and capture the
        # running Discord event loop on_ready.
        apply_manual_ges_sync(runtime, bot)
        # Must follow the manual layer: this makes each competition own its GES
        # links and replaces sync_from_ges with the season-aware implementation.
        apply_season_ges_authority(runtime, bot)

    guild_isolation_patch.apply_guild_isolation_patch = _apply_with_ges
    guild_isolation_patch._ajpa_ges_startup_bridge_installed = True
    print("AJPA startup: GES config + manual sync restored in final runtime layer")
