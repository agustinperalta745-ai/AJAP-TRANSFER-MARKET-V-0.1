"""One-shot importer for moving AJPA persistent data to a new host.

Runs only when AJPA_MIGRATION_TARGET is enabled and both source variables are
present. It downloads the authenticated Railway export and restores its data/
contents into the mounted /data volume. A marker prevents repeated imports.
"""

from __future__ import annotations

import io
import os
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

CUTOVER_FLAG = Path(__file__).resolve().parent / "northflank_cutover_live.flag"


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_members(archive: tarfile.TarFile):
    for member in archive.getmembers():
        name = member.name.replace("\\", "/")
        if name == "data":
            continue
        if not name.startswith("data/"):
            raise RuntimeError(f"Unexpected archive member: {name}")
        rel = name[len("data/"):]
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            raise RuntimeError(f"Unsafe archive member: {name}")
        yield member, rel


def maybe_import_migration_data() -> bool:
    if not _truthy("AJPA_MIGRATION_TARGET"):
        return False

    source = (os.getenv("AJPA_MIGRATION_SOURCE_URL") or "").strip()
    key = (os.getenv("AJPA_MIGRATION_SOURCE_KEY") or "").strip()
    if not source or not key:
        print("AJPA migration target ready: waiting for source URL/key")
        return False

    target = Path("/data")
    target.mkdir(parents=True, exist_ok=True)

    # Once this volume has successfully connected Discord from Northflank, it is
    # production data. Never overwrite it again from the frozen Railway source.
    runtime_marker = target / ".ajpa_runtime_ready"
    if runtime_marker.exists():
        ready = runtime_marker.read_text(encoding="utf-8", errors="replace")
        if "host=northflank" in ready:
            print("AJPA migration finalized on Northflank: source import permanently skipped")
            return True

    marker = target / ".ajpa_migration_imported"
    final_marker = target / ".ajpa_cutover_final_imported"
    is_railway = bool((os.getenv("RAILWAY_PROJECT_ID") or "").strip())
    cutover_live = CUTOVER_FLAG.exists() and not is_railway

    if cutover_live and final_marker.exists():
        print("AJPA cutover final import already completed; preserving Northflank data")
        return True

    force = _truthy("AJPA_MIGRATION_FORCE_IMPORT") or cutover_live
    if marker.exists() and not force:
        print("AJPA migration import already completed; skipping")
        return True
    if force and marker.exists():
        marker.unlink(missing_ok=True)
        print("AJPA migration force import enabled: refreshing snapshot")

    url = source + ("&" if "?" in source else "?") + urllib.parse.urlencode({"key": key})
    print("AJPA migration import: downloading authenticated snapshot")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AJPA-Northflank-Migration/1", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        if getattr(response, "status", 200) != 200:
            raise RuntimeError(f"Migration source HTTP {response.status}")
        payload = response.read()

    restored = 0
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member, rel in _safe_members(archive):
            dest = target / rel
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = archive.extractfile(member)
            if src is None:
                continue
            with src, dest.open("wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            restored += 1

    marker.write_text(f"restored_files={restored}\n", encoding="utf-8")
    if cutover_live:
        final_marker.write_text(f"restored_files={restored}\n", encoding="utf-8")
        print("AJPA migration final cutover snapshot locked on Northflank")
    print(f"AJPA migration import completed: restored_files={restored}")
    return True
