"""Railway runtime defaults and AJAP startup hooks.

Python imports this module automatically at startup (when it is available on
sys.path). It keeps SQLite on the Railway Volume and installs the fixed-team
assignment layer immediately before the Discord bot starts.
"""

import os
from pathlib import Path


volume_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")

if volume_path and not os.getenv("DB_PATH"):
    persistent_db = Path(volume_path) / "ajap_market.db"
    os.environ["DB_PATH"] = str(persistent_db)


# bot.py calls Bot.run() only after its database schema, views and slash commands
# have been defined. Hooking here lets the assignment layer extend that finished
# bot without changing the stable market workflow in bot.py.
try:
    from discord.ext import commands

    _original_bot_run = commands.Bot.run

    def _run_with_ajap_team_assignment(self, token, *args, **kwargs):
        if not getattr(self, "_ajap_fixed_team_patch", False):
            try:
                import __main__
                from team_assignment import apply_team_assignment_patch
                from lyon_test_seed import apply_lyon_test_patch

                apply_team_assignment_patch(__main__, self)
                apply_lyon_test_patch(__main__)
            except Exception as exc:
                # Keep the bot available even if this optional startup layer fails.
                print(f"Error cargando asignación/equipo de prueba: {exc}")
        return _original_bot_run(self, token, *args, **kwargs)

    commands.Bot.run = _run_with_ajap_team_assignment
except ImportError:
    # Lets local tooling inspect the repository even without discord.py installed.
    pass
