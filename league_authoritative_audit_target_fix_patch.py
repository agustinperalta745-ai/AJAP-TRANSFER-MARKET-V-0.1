"""Point the authoritative 03/09 audit at the live AJPA guild and require a real GES wipe.

The first reconciliation was accidentally scoped to the historical legacy guild while
AJPA Mobile/production uses AJPA_MOBILE_GUILD_ID. This bridge runs before Discord
connects, retargets the existing reconciliation to the production guild, forces a v2
one-time marker, and refuses to mark GES complete unless the configured channel is
actually empty before the 38 canonical cards are republished.
"""
from __future__ import annotations

import os

import guild_isolation_patch as guild_isolation
import league_authoritative_audit_reconcile_patch as reconcile


def _production_guild_id() -> int:
    raw = (
        os.getenv("AJPA_MOBILE_GUILD_ID")
        or os.getenv("DISCORD_GUILD_ID")
        or str(guild_isolation.LEGACY_GUILD_ID)
    ).strip()
    return int(raw)


reconcile.TARGET_GUILD_ID = _production_guild_id()
# v2 intentionally re-runs even if an earlier v1 marker happened to exist.
reconcile.MARKER = "authoritative_preseason_audit_2026_09_03_v2_live_guild"


async def _strict_purge_channel(channel):
    """Delete everything and prove the channel is empty before rebuilding it."""
    before = [message async for message in channel.history(limit=None, oldest_first=False)]
    if not before:
        return 0

    deleted_count = 0
    try:
        deleted = await channel.purge(
            limit=None,
            check=lambda _message: True,
            bulk=True,
            reason="AJPA: reconstrucción oficial GES 03/09/2026",
        )
        deleted_count = len(deleted)
    except Exception as bulk_exc:
        print(
            "AJAP GES strict cleanup: bulk purge failed; trying individual deletes: "
            f"{type(bulk_exc).__name__}: {bulk_exc}"
        )
        for message in before:
            try:
                await message.delete()
                deleted_count += 1
            except Exception as exc:
                raise RuntimeError(
                    "GES no pudo limpiarse por completo. "
                    f"message={getattr(message, 'id', '?')} "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

    remaining = [message async for message in channel.history(limit=5, oldest_first=False)]
    if remaining:
        raise RuntimeError(
            "GES cleanup verification failed: todavía quedan mensajes en el canal "
            f"después de intentar borrar {deleted_count}."
        )
    return deleted_count


reconcile._purge_channel = _strict_purge_channel

print(
    "AJPA authoritative audit FIX: live guild="
    f"{reconcile.TARGET_GUILD_ID} • marker=v2 • GES wipe estricto"
)
