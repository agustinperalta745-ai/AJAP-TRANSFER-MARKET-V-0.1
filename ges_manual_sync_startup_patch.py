"""Install the manual GES flow after AJPA's existing guild/liga setup."""

import guild_isolation_patch
import league_ges_parser_hardening_patch  # noqa: F401
import ges_authoritative_snapshot_patch
import ges_new_result_cards_patch

from ges_config_recovery_patch import apply_ges_config_recovery
from league_ges_manual_sync_patch import apply_manual_ges_sync
from legacy_result_intake_disabled_patch import disable_legacy_result_intake
from season_ges_authority_patch import apply_season_ges_authority
from season_ges_snapshot_cleanup_patch import apply_season_snapshot_cleanup
import season_ges_finalizer_patch  # noqa: F401  patches authoritative installer

_BASE_APPLY = guild_isolation_patch.apply_guild_isolation_patch


def _apply_with_manual_ges(runtime, bot):
    _BASE_APPLY(runtime, bot)
    apply_manual_ges_sync(runtime, bot)
    apply_season_ges_authority(runtime, bot)
    apply_season_snapshot_cleanup(runtime, bot)

    # Install the final Mobile GES reader now (not lazily on /app_codigo).
    # season_ges_finalizer_patch restores the seasonal sync immediately after
    # the older snapshot module initializes its read layer.
    ges_authoritative_snapshot_patch.apply_authoritative_ges_snapshot(runtime, bot)
    ges_new_result_cards_patch.apply_ges_new_result_cards(runtime, bot)

    # Last GES safety layer: if an old/mobile DB split left the very first active
    # competition without a persisted config, repair it from the boot URLs once
    # and retry the exact same final sync chain. Future competitions still require
    # their own explicit URLs and never inherit a previous season.
    apply_ges_config_recovery(runtime, bot)

    # Must be last: older Liga patches are allowed to initialize, then their
    # Discord result intake is removed and made inert permanently.
    disable_legacy_result_intake(runtime, bot)


guild_isolation_patch.apply_guild_isolation_patch = _apply_with_manual_ges
print("AJPA startup: manual GES sync will be final Liga intake layer")
