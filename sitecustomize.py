"""Railway runtime defaults and AJAP startup hooks.

AJAP stores SQLite on Railway's persistent Volume. Prefer the mount path
reported by Railway itself and keep /data only as a compatibility fallback.
Never silently fall back to the ephemeral container filesystem on Railway.
Once the persistent Volume contains an AJAP database, that database is
authoritative and is never overwritten by an older copy found elsewhere.

AJAP_DB_FILENAME can select an isolated SQLite file inside the mounted Volume
(for example ``ajap_production.db``). A custom filename intentionally disables
cross-file first-boot recovery so a production database can start clean while
keeping the old test database untouched in the same Volume.
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
    return (
        1 if stats["clubs"] > 0 else 0,
        stats["clubs"],
        stats["history"] + stats["transfers"],
        stats["roster"],
        stats["seeds"],
        priority,
    )


def _usable_directory(path: Path):
    """Return True only for an existing/writable directory suitable for SQLite."""
    try:
        if not path.exists() or not path.is_dir():
            return False
        probe = path / ".ajap_volume_probe"
        with probe.open("a", encoding="utf-8"):
            pass
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _database_filename():
    raw = (os.getenv("AJAP_DB_FILENAME") or "").strip()
    if not raw:
        return "ajap_market.db", False

    # Keep the variable intentionally simple: a filename inside the mounted
    # Volume, never an arbitrary path that could escape persistent storage.
    if Path(raw).name != raw or raw in {".", ".."}:
        raise RuntimeError(
            "AJAP_DB_FILENAME debe ser solo un nombre de archivo, por ejemplo ajap_production.db"
        )
    if not raw.casefold().endswith(".db"):
        raise RuntimeError("AJAP_DB_FILENAME debe terminar en .db")
    return raw, True


def configure_database_path():
    """Resolve the AJAP database and force Railway onto persistent storage."""
    on_railway = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_PROJECT_ID")
        or os.getenv("RAILWAY_DEPLOYMENT_ID")
    )

    db_filename, isolated_filename = _database_filename()
    explicit_raw = (os.getenv("DB_PATH") or "").strip()
    explicit = Path(explicit_raw) if explicit_raw else None
    mount_raw = (os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()
    mount_dir = Path(mount_raw) if mount_raw else None
    mount_db = mount_dir / db_filename if mount_dir else None

    raw_candidates = []
    if mount_db:
        raw_candidates.append(("RAILWAY_VOLUME_MOUNT_PATH", mount_db, 70))
    if explicit:
        raw_candidates.append(("DB_PATH", explicit, 60))

    # Legacy recovery candidates are useful for the historical default DB, but
    # must never be consulted for a deliberately isolated production filename.
    if not isolated_filename:
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
        # Railway exposes the real Volume mount path in RAILWAY_VOLUME_MOUNT_PATH.
        # Use it first instead of assuming every service mounts at /data.
        railway_dirs = []
        if mount_dir:
            railway_dirs.append(("RAILWAY_VOLUME_MOUNT_PATH", mount_dir))
        railway_dirs.extend(
            [
                ("Railway Volume /data", Path("/data")),
                ("Railway Volume /app/data", Path("/app/data")),
                ("Railway Volume /mnt/data", Path("/mnt/data")),
            ]
        )

        seen_dirs = set()
        selected = None
        for source, directory in railway_dirs:
            key = str(directory.resolve(strict=False))
            if key in seen_dirs:
                continue
            seen_dirs.add(key)
            if _usable_directory(directory):
                selected = (source, directory)
                break

        if selected is None:
            reported = mount_raw or "no informado"
            explicit_info = explicit_raw or "no informado"
            raise RuntimeError(
                "AJAP: Railway no expone un Volume persistente utilizable. "
                f"RAILWAY_VOLUME_MOUNT_PATH={reported}; DB_PATH={explicit_info}. "
                "Se detiene el bot para no perder datos en almacenamiento temporal."
            )

        preferred_source, volume_dir = selected
        preferred_target = volume_dir / db_filename
        print(f"AJAP Railway volume detected: {volume_dir} | source={preferred_source}")
        if isolated_filename:
            print(
                f"AJAP isolated database selected by AJAP_DB_FILENAME: {db_filename} | "
                "legacy recovery disabled"
            )
    elif explicit:
        preferred_target = explicit
        preferred_source = "DB_PATH"
    elif mount_db:
        preferred_target = mount_db
        preferred_source = "RAILWAY_VOLUME_MOUNT_PATH"

    if preferred_target:
        target_stats = _db_stats(preferred_target)

        # Recovery is allowed only for the historical/default DB. A custom
        # AJAP_DB_FILENAME is an explicit request for an isolated database and
        # must start empty if the selected file does not exist yet.
        if target_stats is None and best_existing and not isolated_filename:
            _, source_path, source_priority, source_stats = best_existing
            if source_path.resolve(strict=False) != preferred_target.resolve(strict=False):
                try:
                    preferred_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, preferred_target)
                    print(
                        f"AJAP DB first-boot recovery: copied {source_path} -> {preferred_target}"
                    )
                except Exception as exc:
                    print(f"WARNING AJAP: no se pudo recuperar DB hacia {preferred_target}: {exc}")

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

    fallback = Path(db_filename)
    os.environ["DB_PATH"] = str(fallback)
    print(f"AJAP local database selected: {db_filename}")
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
                from league_known_feyenoord_fulham_scorer_fix_patch import _install as install_feyenoord_fulham_scorers
                from league_known_ajax_feyenoord_score_repairs_patch import _install as install_ajax_feyenoord_repairs
                import league_period_sum_score_guard_patch  # noqa: F401

                enable_additional_teams()
                apply_team_assignment_patch(__main__, self)
                apply_lyon_test_patch(__main__)
                seed_additional_rosters(__main__)
                apply_publish_ovr_patch(__main__)
                install_feyenoord_fulham_scorers(__main__, self)
                install_ajax_feyenoord_repairs(__main__, self)
            except Exception as exc:
                print(f"Error cargando equipos/plantillas AJAP: {exc}")
        return _original_bot_run(self, token, *args, **kwargs)

    commands.Bot.run = _run_with_ajap_team_assignment
except ImportError:
    pass
