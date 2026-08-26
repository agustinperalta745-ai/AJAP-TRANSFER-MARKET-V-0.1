"""Railway compatibility entry point.

Railway is currently configured to start `python bot.py`. Keep that command
working, but route startup through run_bot.py so the Lyon selector/roster
patches are applied before Discord connects.
"""

# Patch nickname flows before run_bot registers Discord commands/views.
import member_nickname_patch  # noqa: F401
import vacancy_nickname_patch  # noqa: F401
import selector_nickname_patch  # noqa: F401
import run_bot  # noqa: F401
