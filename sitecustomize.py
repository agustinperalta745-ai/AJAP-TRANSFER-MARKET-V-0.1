"""Railway runtime defaults and AJAP startup hooks.

Python imports this module automatically at startup (when it is available on
sys.path). AJAP's production SQLite database must live on the Railway Volume so
deploys/restarts can never reset club assignments, rosters or market history.
"""

import os
from pathlib import Path


def configure_database_path():
    """Pin AJAP to persistent Railway storage whenever the /data volume exists."""
    on_railway = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_PROJECT_ID")
        or os.getenv("RAILWAY_DEPLOYMENT_ID")
    )

    # AJAP's Railway Volume was created at /data. On Railway this path is the
    # source of truth and MUST beat an old/misconfigured DB_PATH variable.
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

    # Support a Railway volume mounted somewhere other than /data if the
    # service configuration ever changes in the future.
    mount_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if on_railway and mount_path:
        volume_dir = Path(mount_path)
        volume_dir.mkdir(parents=True, exist_ok=True)
        db_path = volume_dir / "ajap_market.db"
        os.environ["DB_PATH"] = str(db_path)
        print(f"AJAP database: {db_path} | source=RAILWAY_VOLUME_MOUNT_PATH")
        return db_path

    # Outside Railway, an explicit path remains useful for local development.
    explicit = os.getenv("DB_PATH")
    if explicit:
        db_path = Path(explicit)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"AJAP database: {db_path} | source=DB_PATH")
        return db_path

    db_path = Path("ajap_market.db")
    os.environ["DB_PATH"] = str(db_path)
    if on_railway:
        print(
            "WARNING AJAP: Railway is running WITHOUT the /data volume; "
            f"using non-persistent fallback {db_path}"
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
