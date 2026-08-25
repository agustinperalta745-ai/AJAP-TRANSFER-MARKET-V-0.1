"""Legacy Railway entry point.

Some older AJAP services may still be configured to start `python bot_core.py`.
Never launch a second, unpatched copy of the Discord bot from here: route every
legacy start command through the same canonical runtime used by bot.py.
"""

import run_bot  # noqa: F401
