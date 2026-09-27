"""Durable AJPA Mobile -> Discord bridge for newly created market offers.

Mobile HTTP handlers only mutate SQLite. Each app-created offer is queued in the
same transaction, then this worker delivers the canonical Discord seller DM once
the bot is connected. Because it calls offer_notifications dynamically, the
final inline negotiation patch is reused too (Aceptar / Contraofertar / Rechazar).
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from discord.ext import tasks

import guild_isolation_patch
import market_rumor_patch
import mobile_write_api
import offer_notifications_patch as offer_notifications

APP = None
BOT = None


def _pending_events(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    mobile_write_api.ensure_schema(conn)
    rows = conn.execute(
        """
        SELECT id, offer_id, attempts
        FROM mobile_offer_discord_outbox
        WHERE status='PENDING'
          AND datetime(next_attempt_at) <= datetime('now')
        ORDER BY id ASC
        LIMIT ?
        """,
        (max(1, min(int(limit), 100)),),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "offer_id": int(row["offer_id"]),
            "attempts": int(row["attempts"] or 0),
        }
        for row in rows
    ]


def _mark_processed(
    conn: sqlite3.Connection,
    event_id: int,
    status: str = "SENT",
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE mobile_offer_discord_outbox
        SET status=?,
            last_error=?,
            processed_at=CURRENT_TIMESTAMP
        WHERE id=? AND status='PENDING'
        """,
        (status, error, int(event_id)),
    )
    conn.commit()


def _mark_retry(
    conn: sqlite3.Connection,
    event_id: int,
    attempts: int,
    error: str,
) -> None:
    next_attempt = int(attempts) + 1
    if next_attempt >= 5:
        conn.execute(
            """
            UPDATE mobile_offer_discord_outbox
            SET status='FAILED',
                attempts=?,
                last_error=?,
                processed_at=CURRENT_TIMESTAMP
            WHERE id=? AND status='PENDING'
            """,
            (next_attempt, str(error)[:500], int(event_id)),
        )
    else:
        conn.execute(
            """
            UPDATE mobile_offer_discord_outbox
            SET attempts=?,
                last_error=?,
                next_attempt_at=datetime('now', '+30 seconds')
            WHERE id=? AND status='PENDING'
            """,
            (next_attempt, str(error)[:500], int(event_id)),
        )
    conn.commit()


async def sync_guild(guild) -> None:
    if APP is None or BOT is None:
        return

    conn = APP.db_for_guild(guild.id)
    try:
        conn.row_factory = sqlite3.Row
        events = _pending_events(conn)
        conn.commit()
    finally:
        conn.close()

    for event in events:
        event_id = int(event["id"])
        offer_id = int(event["offer_id"])
        attempts = int(event["attempts"])

        conn = APP.db_for_guild(guild.id)
        try:
            conn.row_factory = sqlite3.Row
            offer = conn.execute(
                "SELECT * FROM offers WHERE id=? LIMIT 1",
                (offer_id,),
            ).fetchone()

            if offer is None:
                _mark_processed(
                    conn,
                    event_id,
                    "SKIPPED_MISSING",
                    "La oferta ya no existe.",
                )
                continue

            if str(offer["status"] or "").upper() != "PENDIENTE":
                _mark_processed(
                    conn,
                    event_id,
                    "SKIPPED_RESOLVED",
                    f"Estado actual: {offer['status']}",
                )
                continue
        finally:
            conn.close()

        try:
            with guild_isolation_patch.guild_context(guild.id):
                sent = bool(await offer_notifications._send_seller_dm(offer))
                # App offers have no Discord source channel, so mirror their
                # public side through the canonical deduplicated market rumor.
                try:
                    await market_rumor_patch.publish_offer_rumor(
                        SimpleNamespace(guild=guild),
                        offer,
                    )
                except Exception as rumor_exc:
                    print(
                        f"WARNING AJPA: rumor de oferta mobile #{offer_id} fallo: "
                        f"{type(rumor_exc).__name__}: {rumor_exc}"
                    )
        except Exception as exc:
            sent = False
            error = f"{type(exc).__name__}: {exc}"
        else:
            error = None if sent else "Discord no pudo entregar el DM al vendedor."

        conn = APP.db_for_guild(guild.id)
        try:
            conn.row_factory = sqlite3.Row
            if sent:
                _mark_processed(conn, event_id, "SENT")
                print(
                    f"AJPA mobile offer bridge: oferta #{offer_id} enviada por DM "
                    f"guild={guild.id}"
                )
            else:
                _mark_retry(
                    conn,
                    event_id,
                    attempts,
                    error or "No se pudo entregar la oferta en Discord.",
                )
        finally:
            conn.close()


def apply_mobile_offer_discord_bridge(runtime, bot) -> None:
    global APP, BOT
    if getattr(runtime, "_ajpa_mobile_offer_discord_bridge", False):
        return

    APP = runtime
    BOT = bot

    @tasks.loop(seconds=3)
    async def mobile_offer_worker():
        if not bot.is_ready():
            return
        for guild in list(bot.guilds):
            try:
                await sync_guild(guild)
            except Exception as exc:
                print(
                    "AJPA mobile offer bridge error | "
                    f"guild={getattr(guild, 'id', '?')} | "
                    f"{type(exc).__name__}: {exc}"
                )

    async def on_ready():
        for guild in list(bot.guilds):
            try:
                await sync_guild(guild)
            except Exception as exc:
                print(
                    "AJPA mobile offer initial sync error | "
                    f"guild={getattr(guild, 'id', '?')} | "
                    f"{type(exc).__name__}: {exc}"
                )
        if not mobile_offer_worker.is_running():
            mobile_offer_worker.start()

    bot.add_listener(on_ready, "on_ready")
    runtime._ajpa_mobile_offer_discord_bridge = True
    runtime._ajpa_mobile_offer_discord_worker = mobile_offer_worker
    print("AJPA: ofertas App -> Discord DM bridge activo")


_original_apply_guild_isolation_patch = guild_isolation_patch.apply_guild_isolation_patch


def _apply_guild_isolation_then_mobile_offer_bridge(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_mobile_offer_discord_bridge(runtime, bot)


if not getattr(guild_isolation_patch, "_ajpa_mobile_offer_bridge_wrapped", False):
    guild_isolation_patch.apply_guild_isolation_patch = (
        _apply_guild_isolation_then_mobile_offer_bridge
    )
    guild_isolation_patch._ajpa_mobile_offer_bridge_wrapped = True
