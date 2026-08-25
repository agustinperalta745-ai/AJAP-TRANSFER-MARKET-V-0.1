"""Railway runtime defaults and AJAP startup hooks.

Python imports this module automatically at startup (when it is available on
sys.path). AJAP's production SQLite database should live on the Railway Volume
so deploys/restarts preserve club assignments, rosters and market history.
"""

import os
from pathlib import Path


def configure_database_path():
    """Prefer AJAP's persistent Railway volume without ever crashing startup."""
    on_railway = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_PROJECT_ID")
        or os.getenv("RAILWAY_DEPLOYMENT_ID")
    )

    # This is the mount path already used by the AJAP Railway service and the
    # last configuration that was confirmed to boot correctly.
    data_dir = Path("/data")
    if on_railway and data_dir.exists() and data_dir.is_dir():
        db_path = data_dir / "ajap_market.db"
        previous = os.getenv("DB_PATH")
        os.environ["DB_PATH"] = str(db_path)
        print(
            f"AJAP database: {db_path} | source=FORCED_RAILWAY_VOLUME"
            + (f" | ignored DB_PATH={previous}" if previous and previous != str(db_path) else "")
        )
        return db_path

    # Support Railway if it exposes the attached volume through its runtime var.
    mount_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if on_railway and mount_path:
        volume_dir = Path(mount_path)
        volume_dir.mkdir(parents=True, exist_ok=True)
        db_path = volume_dir / "ajap_market.db"
        os.environ["DB_PATH"] = str(db_path)
        print(f"AJAP database: {db_path} | source=RAILWAY_VOLUME_MOUNT_PATH")
        return db_path

    # An explicitly configured DB_PATH is still valid.
    explicit = os.getenv("DB_PATH")
    if explicit:
        db_path = Path(explicit)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"AJAP database: {db_path} | source=DB_PATH")
        return db_path

    # Never kill the whole Discord bot from sitecustomize. If Railway ever boots
    # without seeing the volume, stay online and print a loud diagnostic instead.
    db_path = Path("ajap_market.db")
    os.environ["DB_PATH"] = str(db_path)
    if on_railway:
        print(
            "WARNING AJAP: Railway volume not detected at startup; "
            f"using fallback database {db_path}. CHECK VOLUME CONFIGURATION."
        )
    else:
        print(f"AJAP database: {db_path} | source=local fallback")
    return db_path


configure_database_path()


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
                from publish_ovr_patch import apply_publish_ovr_patch

                enable_additional_teams()
                apply_team_assignment_patch(__main__, self)
                apply_lyon_test_patch(__main__)
                seed_additional_rosters(__main__)
                apply_publish_ovr_patch(__main__)
            except Exception as exc:
                print(f"Error cargando equipos/plantillas AJAP: {exc}")
        return _original_bot_run(self, token, *args, **kwargs)

    commands.Bot.run = _run_with_ajap_team_assignment
except ImportError:
    pass
