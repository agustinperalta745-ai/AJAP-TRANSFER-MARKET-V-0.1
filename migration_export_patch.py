"""Temporary authenticated export endpoint for AJPA host migration.

Enabled only when AJPA_MIGRATION_EXPORT_KEY is present. Produces a consistent
archive of the persistent data directory. SQLite databases are copied with the
SQLite backup API so the live Railway service can keep running during export.
"""

from __future__ import annotations

import io
import os
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import mobile_read_api


def _enabled_key() -> str:
    return (os.getenv("AJPA_MIGRATION_EXPORT_KEY") or "").strip()


def _data_dir() -> Path:
    raw = (
        os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
        or os.getenv("AJPA_DATA_DIR")
        or "/data"
    ).strip()
    return Path(raw)


def _snapshot_archive() -> bytes:
    source = _data_dir()
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"Persistent data directory not found: {source}")

    with tempfile.TemporaryDirectory(prefix="ajpa-migrate-") as tmp:
        snap = Path(tmp) / "data"
        snap.mkdir(parents=True, exist_ok=True)

        for item in source.rglob("*"):
            rel = item.relative_to(source)
            target = snap / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not item.is_file():
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            if item.suffix.casefold() == ".db":
                src = sqlite3.connect(str(item), timeout=30)
                try:
                    dst = sqlite3.connect(str(target))
                    try:
                        src.backup(dst)
                    finally:
                        dst.close()
                finally:
                    src.close()
            else:
                shutil.copy2(item, target)

        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode="w:gz") as tar:
            tar.add(snap, arcname="data")
        return out.getvalue()


def apply_migration_export_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_migration_export_patch", False):
        return

    original_get = handler.do_GET

    def migration_get(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/v1/migration/status":
            data_dir = _data_dir()
            db_path = Path(os.getenv("DB_PATH") or (data_dir / "ajap_market.db"))
            marker = data_dir / ".ajpa_migration_imported"
            payload = {
                "target_mode": (os.getenv("AJPA_MIGRATION_TARGET") or "").strip().lower() in {"1","true","yes","on"},
                "data_dir": str(data_dir),
                "db_path": str(db_path),
                "db_exists": db_path.exists(),
                "db_size": db_path.stat().st_size if db_path.exists() else 0,
                "import_marker": marker.exists(),
            }
            try:
                if db_path.exists():
                    with sqlite3.connect(str(db_path)) as conn:
                        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        for table in ("roster_players","publications","offers","transfers","clubs"):
                            if table in tables:
                                payload[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except Exception as exc:
                payload["db_error"] = f"{type(exc).__name__}: {exc}"
            self._json(payload)
            return

        if path != "/api/v1/migration/export":
            return original_get(self)

        key = _enabled_key()
        supplied = (parse_qs(parsed.query).get("key") or [""])[0]
        if not key or supplied != key:
            self._json({"error": "not_found"}, 404)
            return

        try:
            body = _snapshot_archive()
        except Exception as exc:
            print(f"AJPA migration export failed: {type(exc).__name__}: {exc}")
            self._json({"error": "migration_export_failed"}, 500)
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/gzip")
        self.send_header(
            "Content-Disposition",
            'attachment; filename="ajpa-data-migration.tar.gz"',
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    handler.do_GET = migration_get
    handler._ajpa_migration_export_patch = True
    print("AJPA migration export endpoint armed (only when key is configured)")
