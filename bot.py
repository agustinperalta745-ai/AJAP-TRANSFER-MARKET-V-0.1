"""Railway compatibility entry point.

Railway is currently configured to start `python bot.py`. Keep that command
working, but route startup through run_bot.py so the Lyon selector/roster
patches are applied before Discord connects.
"""

import run_bot  # noqa: F401
