"""Railway compatibility entry point.

Railway is currently configured to start `python bot.py`. Keep that command
working, but route startup through run_bot.py so the Lyon selector/roster
patches are applied before Discord connects.
"""

# Extend the fixed-team selector/seed before Bot.run() installs team assignment.
# Import order matters: Everton wraps Newcastle's seed wrapper, so both rosters
# are preserved in the same startup chain.
import newcastle_extension  # noqa: F401
import everton_extension  # noqa: F401

# Patch nickname/vacancy flows before run_bot registers Discord commands/views.
import member_nickname_patch  # noqa: F401
import vacancy_nickname_patch  # noqa: F401
import selector_nickname_patch  # noqa: F401
import dt_resignation_patch  # noqa: F401
import run_bot  # noqa: F401
