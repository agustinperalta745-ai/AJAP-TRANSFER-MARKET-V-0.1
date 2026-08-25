"""Railway runtime defaults and AJAP startup hooks.

Python imports this module automatically at startup (when it is available on
sys.path). It keeps SQLite on the Railway Volume when available and installs
the AJAP runtime patches before the Discord bot starts.
"""

import os
from pathlib import Path


def configure_database_path():
    """Choose a persistent DB path when available without ever crashing startup."""
    # 1) Explicit DB_PATH always wins. If Railway was already configured with a
    # persistent path, do not overwrite it.
    explicit = os.getenv("DB_PATH")
    if explicit:
        db_path = Path(explicit)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"AJAP database: {db_path} | source=DB_PATH")
        return db_path

    on_railway = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_PROJECT_ID")
        or os.getenv("RAILWAY_DEPLOYMENT_ID")
    )

    # 2) Prefer Railway's real mounted-volume path when exposed.
    mount_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if on_railway and mount_path:
        volume_dir = Path(mount_path)
        volume_dir.mkdir(parents=True, exist_ok=True)
        db_path = volume_dir / "ajap_market.db"
        os.environ["DB_PATH"] = str(db_path)
        print(f"AJAP database: {db_path} | source=RAILWAY_VOLUME_MOUNT_PATH")
        return db_path

    # 3) Compatibility fallback for the AJAP service, where the Railway volume
    # has been mounted at /data. Do not require Path.is_mount(); bind mounts may
    # not be reported as mounts from inside every container runtime.
    data_dir = Path("/data")
    if on_railway and data_dir.exists() and data_dir.is_dir():
        db_path = data_dir / "ajap_market.db"
        os.environ["DB_PATH"] = str(db_path)
        print(f"AJAP database: {db_path} | source=/data fallback")
        return db_path

    # 4) Last-resort fallback. The bot must remain online instead of crashing.
    # The log makes it obvious that Railway's persistent mount still needs review.
    db_path = Path("ajap_market.db")
    os.environ["DB_PATH"] = str(db_path)
    print(
        "WARNING AJAP: Railway volume path not detected; "
        f"using fallback database {db_path}"
    )
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
