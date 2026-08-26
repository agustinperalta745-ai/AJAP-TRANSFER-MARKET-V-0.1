"""Railway compatibility entry point.

Railway is currently configured to start `python bot.py`. Keep that command
working, but route startup through run_bot.py so the AJAP patches are applied
before Discord connects.
"""

# Extend the fixed-team selector/seed before Bot.run() installs team assignment.
# Import order matters: Everton wraps Newcastle's seed wrapper, so both rosters
# are preserved in the same startup chain.
import newcastle_extension  # noqa: F401
import everton_extension  # noqa: F401
# Existing per-guild DBs need a one-time safe sync for teams added later.
import additional_roster_sync_patch  # noqa: F401

# Patch nickname/vacancy flows before run_bot registers Discord commands/views.
import member_nickname_patch  # noqa: F401
import vacancy_nickname_patch  # noqa: F401
import selector_nickname_patch  # noqa: F401
import dt_resignation_patch  # noqa: F401

# Liga AJAP usa el mismo bot, pero queda separada del mercado. La envolvemos
# alrededor del aislamiento por servidor para que sus tablas/resultados también
# queden persistidos en la DB correspondiente a cada servidor de Discord.
import guild_isolation_patch
from league_automation_patch import apply_league_automation_patch

_original_apply_guild_isolation_patch = guild_isolation_patch.apply_guild_isolation_patch


def _apply_guild_isolation_and_league(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_league_automation_patch(runtime, bot)


guild_isolation_patch.apply_guild_isolation_patch = _apply_guild_isolation_and_league

import run_bot  # noqa: F401,E402
