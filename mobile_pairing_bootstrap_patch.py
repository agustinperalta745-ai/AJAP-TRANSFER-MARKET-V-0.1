"""Attach /app_codigo after guild isolation is installed.

bot_mobile imports this module before bot.py/run_bot.py. It wraps the final guild
isolation hook so the pairing command is registered against the real runtime and
therefore participates in the same per-guild SQLite context as the Discord bot.
"""

import guild_isolation_patch
import mobile_pairing_patch


_original = guild_isolation_patch.apply_guild_isolation_patch


if not getattr(_original, "_ajpa_mobile_pairing_wrapped", False):
    def _with_mobile_pairing(runtime, bot):
        _original(runtime, bot)
        mobile_pairing_patch.apply_mobile_pairing_patch(runtime, bot)

    _with_mobile_pairing._ajpa_mobile_pairing_wrapped = True
    guild_isolation_patch.apply_guild_isolation_patch = _with_mobile_pairing
