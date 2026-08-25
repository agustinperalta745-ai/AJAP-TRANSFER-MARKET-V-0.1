"""Railway runtime defaults and AJAP startup hooks.

Python imports this module automatically at startup (when it is available on
sys.path). It keeps SQLite on the Railway Volume and installs the fixed-team
assignment layer immediately before the Discord bot starts.
"""

import os
from pathlib import Path


# AJAP's Railway Volume is mounted at /data. Always use that exact path in
# Railway so club assignments, rosters and market state survive redeploys.
# Do not allow a stale DB_PATH variable to send SQLite back to ephemeral storage.
if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID") or Path("/data").exists():
    persistent_db = Path("/data") / "ajap_market.db"
    persistent_db.parent.mkdir(parents=True, exist_ok=True)
    os.environ["DB_PATH"] = str(persistent_db)
else:
    # Local development fallback only.
    os.environ.setdefault("DB_PATH", "ajap_market.db")

print(f"AJAP persistent database: {os.environ['DB_PATH']}")


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
                from multi_team_extension import enable_additional_teams, seed_additional_rosters

                enable_additional_teams()
                apply_team_assignment_patch(__main__, self)
                apply_lyon_test_patch(__main__)
                seed_additional_rosters(__main__)
            except Exception as exc:
                # Keep the bot available even if this optional startup layer fails.
                print(f"Error cargando equipos/plantillas AJAP: {exc}")
        return _original_bot_run(self, token, *args, **kwargs)

    commands.Bot.run = _run_with_ajap_team_assignment
except ImportError:
    # Lets local tooling inspect the repository even without discord.py installed.
    pass
