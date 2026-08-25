"""Railway runtime defaults and AJAP startup hooks.

AJAP's Railway service has a persistent Volume mounted at /data. On Railway we
always store SQLite at /data/ajap_market.db and never silently fall back to the
container filesystem. Local/non-Railway runs can still use DB_PATH or a local DB.
"""

import os
import shutil
import sqlite3
from pathlib import Path


def _db_stats(path: Path):
    """Return lightweight evidence about an existing AJAP SQLite database."""
    try:
        if not path.exists() or not path.is_file() or path.stat().st_size == 0:
            return None
        with sqlite3.connect(str(path)) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if not tables:
                return None

            def count(table):
                if table not in tables:
                    return 0
                return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

            return {
                "clubs": count("clubs"),
                "roster": count("roster_players"),
                "transfers": count("transfers"),
                "history": count("player_history"),
                "seeds": count("seed_state"),
                "mtime": path.stat().st_mtime,
            }
    except Exception as exc:
        print(f"WARNING AJAP: no se pudo inspeccionar DB {path}: {exc}")
        return None


def _score(stats, priority):
    if not stats:
        return (-1, -1, -1, -1, -1, priority)
    # Existing user assignments are the strongest signal. Then prefer the DB
    # carrying the largest amount of real league state.
    return (
        1 if stats["clubs"] > 0 else 0,
        stats["clubs"],
        stats["history"] + stats["transfers"],
        stats["roster"],
        stats["seeds"],
        priority,
    )


def configure_database_path():
    """Resolve the AJAP database and force Railway onto its persistent Volume."""
    on_railway = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_PROJECT_ID")
        or os.getenv("RAILWAY_DEPLOYMENT_ID")
    )

    explicit_raw = (os.getenv("DB_PATH") or "").strip()
    explicit = Path(explicit_raw) if explicit_raw else None
    mount_raw = (os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()
    mount_db = Path(mount_raw) / "ajap_market.db" if mount_raw else None

    raw_candidates = []
    if mount_db:
        raw_candidates.append(("RAILWAY_VOLUME_MOUNT_PATH", mount_db, 60))
    if explicit:
        raw_candidates.append(("DB_PATH", explicit, 55))
    raw_candidates.extend(
        [
            ("/data", Path("/data/ajap_market.db"), 50),
            ("/app/data", Path("/app/data/ajap_market.db"), 35),
            ("/mnt/data", Path("/mnt/data/ajap_market.db"), 30),
            ("local", Path("ajap_market.db"), 10),
        ]
    )

    candidates = []
    seen = set()
    for label, path, priority in raw_candidates:
        key = str(path.resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        stats = _db_stats(path)
        candidates.append((label, path, priority, stats))
        if stats:
            print(
                f"AJAP DB candidate: {path} | source={label} | "
                f"clubs={stats['clubs']} roster={stats['roster']} "
                f"transfers={stats['transfers']} history={stats['history']}"
            )

    existing = [item for item in candidates if item[3] is not None]
    best_existing = max(existing, key=lambda item: _score(item[3], item[2])) if existing else None

    preferred_target = None
    preferred_source = None

    if on_railway:
        # This AJAP project is explicitly configured in Railway with its Volume
        # mounted at /data. Do not depend on os.path.ismount()/Path.is_mount():
        # bind mounts are not detected reliably on every Linux/container setup.
        volume_dir = Path("/data")
        if not volume_dir.exists():
            raise RuntimeError(
                "AJAP: el Volume de Railway esperado en /data no está montado. "
                "Se detiene el bot para no perder datos en almacenamiento temporal."
            )
        preferred_target = volume_dir / "ajap_market.db"
        preferred_source = "Railway Volume /data"
    elif explicit:
        preferred_target = explicit
        preferred_source = "DB_PATH"
    elif mount_db:
        preferred_target = mount_db
        preferred_source = "RAILWAY_VOLUME_MOUNT_PATH"

    # If another existing AJAP DB contains richer state, recover it into the
    # authoritative destination before opening SQLite there.
    if preferred_target:
        if best_existing:
            _, source_path, source_priority, source_stats = best_existing
            target_stats = _db_stats(preferred_target)
            if source_path.resolve(strict=False) != preferred_target.resolve(strict=False):
                if _score(source_stats, source_priority) > _score(target_stats, 100):
                    try:
                        preferred_target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_path, preferred_target)
                        print(
                            f"AJAP DB recovery: copied {source_path} -> {preferred_target} "
                            f"because source had richer persistent state"
                        )
                    except Exception as exc:
                        print(f"WARNING AJAP: no se pudo recuperar DB hacia {preferred_target}: {exc}")

        # Important: select the persistent target even on the very first boot.
        # The previous logic only selected it when a DB already existed, which
        # let a fresh /data Volume fall through to ephemeral ajap_market.db.
        preferred_target.parent.mkdir(parents=True, exist_ok=True)
        os.environ["DB_PATH"] = str(preferred_target)
        stats = _db_stats(preferred_target)
        print(
            f"AJAP database selected: {preferred_target} | source={preferred_source} | "
            f"clubs={(stats or {}).get('clubs', 0)} roster={(stats or {}).get('roster', 0)}"
        )
        return preferred_target

    # Non-Railway recovery fallback only.
    if best_existing:
        label, path, _, stats = best_existing
        os.environ["DB_PATH"] = str(path)
        print(
            f"AJAP database selected: {path} | recovered_source={label} | "
            f"clubs={stats['clubs']} roster={stats['roster']}"
        )
        return path

    fallback = Path("ajap_market.db")
    os.environ["DB_PATH"] = str(fallback)
    print("AJAP local database selected: ajap_market.db")
    return fallback


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
