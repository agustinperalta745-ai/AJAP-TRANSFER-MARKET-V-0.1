"""Install the manual GES flow after AJPA's existing guild/liga setup."""

import guild_isolation_patch

from league_ges_manual_sync_patch import apply_manual_ges_sync
from legacy_result_intake_disabled_patch import disable_legacy_result_intake

_BASE_APPLY = guild_isolation_patch.apply_guild_isolation_patch


def _apply_with_manual_ges(runtime, bot):
    _BASE_APPLY(runtime, bot)
    apply_manual_ges_sync(runtime, bot)
    # Must be last: older Liga patches are allowed to initialize, then their
    # Discord result intake is removed and made inert permanently.
    disable_legacy_result_intake(runtime, bot)


guild_isolation_patch.apply_guild_isolation_patch = _apply_with_manual_ges
print("AJPA startup: manual GES sync will be final Liga intake layer")
