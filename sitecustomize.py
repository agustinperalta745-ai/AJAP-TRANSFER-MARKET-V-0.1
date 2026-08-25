"""Railway runtime defaults and AJAP startup hooks.

Python imports this module automatically at startup (when it is available on
sys.path). It keeps SQLite on the real Railway Volume and installs the AJAP
runtime patches before the Discord bot starts.
"""

import os
from pathlib import Path


def configure_database_path():
    """Point SQLite at the actual Railway Volume, never ephemeral storage."""
    on_railway = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_PROJECT_ID")
        or os.getenv("RAILWAY_DEPLOYMENT_ID")
    )

    if not on_railway:
        os.environ.setdefault("DB_PATH", "ajap_market.db")
        return Path(os.environ["DB_PATH"])

    # Railway provides this automatically when a Volume is attached. This is the
    # authoritative mount path and may be /data, /app/data or another configured
    # path. Never hard-code /data just because that directory happens to exist.
    mount_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if mount_path:
        volume_dir = Path(mount_path)
    elif Path("/data").is_mount():
        # Compatibility fallback only when /data is confirmed to be a real mount.
        volume_dir = Path("/data")
    else:
        # Failing loudly is safer than starting with an ephemeral SQLite file and
        # silently losing club assignments on the next deploy.
        raise RuntimeError(
            "AJAP necesita un Railway Volume adjunto al servicio. "
            "RAILWAY_VOLUME_MOUNT_PATH no está disponible."
        )

    volume_dir.mkdir(parents=True, exist_ok=True)
    persistent_db = volume_dir / "ajap_market.db"
    os.environ["DB_PATH"] = str(persistent_db)

    # Persistent marker: subsequent deploys must see this same file.
    marker = volume_dir / ".ajap_volume_ready"
    first_seen = not marker.exists()
    if first_seen:
        marker.write_text("AJAP persistent volume initialized\n", encoding="utf-8")

    print(
        "AJAP persistent database: "
        f"{persistent_db} | volume={os.getenv('RAILWAY_VOLUME_NAME', 'attached')} "
        f"| existing_volume={'no' if first_seen else 'yes'}"
    )
    return persistent_db


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
