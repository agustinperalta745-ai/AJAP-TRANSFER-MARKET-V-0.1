"""Reliability guard for automatic_backup_patch."""

from __future__ import annotations

import asyncio
import threading

import automatic_backup_patch as backups


_IO_LOCK = threading.RLock()
_ORIGINAL_CREATE = backups._create_backup_sync
_ORIGINAL_RESTORE = backups._restore_backup_sync
_ORIGINAL_START = backups._start_backup_loop


def _locked_create(*args, **kwargs):
    with _IO_LOCK:
        return _ORIGINAL_CREATE(*args, **kwargs)


def _locked_restore(*args, **kwargs):
    # _ORIGINAL_RESTORE creates a safety backup through backups._create_backup_sync.
    # RLock is intentional so that nested safety copy is safe and non-deadlocking.
    with _IO_LOCK:
        return _ORIGINAL_RESTORE(*args, **kwargs)


async def _delayed_first_start():
    # on_ready listeners can run concurrently. Give guild migrations / one-time V1
    # reset a short head start before taking the first snapshot of the process.
    if backups._BACKUP_TASK is None or backups._BACKUP_TASK.done():
        await asyncio.sleep(8)
    return await _ORIGINAL_START()


backups._create_backup_sync = _locked_create
backups._restore_backup_sync = _locked_restore
backups._start_backup_loop = _delayed_first_start

print("AJAP backup reliability activa: IO serializado + primer snapshot post-migraciones")
