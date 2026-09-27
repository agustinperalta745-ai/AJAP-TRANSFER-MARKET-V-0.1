"""Unified withdrawal flow for AJPA market offers.

Both Discord and AJPA Mobile call the same state transition:
PENDIENTE -> RETIRADA, only by the club/user that created the offer.

A durable outbox then notifies the seller by DM and mirrors the withdrawal in
the configured market channel. The outbox is shared by both interfaces.
"""

from __future__ import annotations

import sqlite3

import discord
from discord.ext import tasks

import guild_isolation_patch

APP = None
BOT = None


class OfferWithdrawalError(Exception):
    pass


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS offer_withdrawal_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER NOT NULL UNIQUE,
            dm_sent INTEGER NOT NULL DEFAULT 0,
            public_sent INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            next_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_offer_withdrawal_outbox_pending
        ON offer_withdrawal_outbox(status, next_attempt_at, id)
        """
    )


def withdraw_offer(conn: sqlite3.Connection, user_id: int, offer_id: int):
    """Atomically withdraw one pending offer and queue its shared notification."""
    ensure_schema(conn)
    offer = conn.execute(
        "SELECT * FROM offers WHERE id=? LIMIT 1",
        (int(offer_id),),
    ).fetchone()
    if offer is None:
        raise OfferWithdrawalError("La oferta no existe.")
    if int(offer["from_id"]) != int(user_id):
        raise OfferWithdrawalError("Solo el club que hizo la oferta puede retirarla.")
    if str(offer["status"] or "").upper() != "PENDIENTE":
        raise OfferWithdrawalError(
            "La oferta ya no está pendiente y no se puede retirar."
        )

    updated = conn.execute(
        """
        UPDATE offers
        SET status='RETIRADA'
        WHERE id=? AND from_id=? AND status='PENDIENTE'
        """,
        (int(offer_id), int(user_id)),
    )
    if int(updated.rowcount or 0) != 1:
        raise OfferWithdrawalError(
            "La oferta cambió de estado antes de poder retirarla."
        )

    conn.execute(
        "INSERT OR IGNORE INTO offer_withdrawal_outbox(offer_id) VALUES(?)",
        (int(offer_id),),
    )

    snapshot = dict(offer)
    snapshot["status"] = "RETIRADA"
    return snapshot


def _withdrawal_embed(runtime, offer) -> discord.Embed:
    embed = discord.Embed(
        title="↩️ OFERTA RETIRADA",
        description=(
            f"**{offer['from_club']}** retiró su oferta por "
            f"**{offer['player']}**."
        ),
        color=discord.Color.dark_grey(),
    )
    summary = getattr(runtime, "offer_summary", None)
    if callable(summary):
        try:
            embed.add_field(
                name="Propuesta retirada",
                value=summary(offer),
                inline=False,
            )
        except Exception:
            embed.add_field(
                name="Monto",
                value=str(offer["amount"] or "$0"),
                inline=True,
            )
    else:
        embed.add_field(
            name="Monto",
            value=str(offer["amount"] or "$0"),
            inline=True,
        )

    embed.add_field(name="Estado", value="↩️ RETIRADA", inline=True)
    embed.add_field(
        name="Resultado",
        value="La negociación quedó cerrada y ya no puede aceptarse ni contraofertarse.",
        inline=False,
    )
    embed.set_footer(text=f"Oferta #{offer['id']} • AJPA Transfer Market")
    return embed


async def _resolve_market_channel(runtime, bot, guild):
    resolver = getattr(runtime, "market_usage_channel_id", None)
    channel_id = None
    if callable(resolver):
        try:
            with guild_isolation_patch.guild_context(guild.id):
                channel_id = resolver(guild.id)
        except Exception as exc:
            print(
                "WARNING AJPA retiro oferta: no pude resolver canal mercado "
                f"guild={guild.id} error={type(exc).__name__}: {exc}"
            )
    if not channel_id:
        return None

    channel = guild.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return channel if hasattr(channel, "send") else None


def _pending_events(conn: sqlite3.Connection, limit: int = 25):
    ensure_schema(conn)
    return conn.execute(
        """
        SELECT id, offer_id, dm_sent, public_sent, attempts
        FROM offer_withdrawal_outbox
        WHERE status='PENDING'
          AND datetime(next_attempt_at) <= datetime('now')
        ORDER BY id ASC
        LIMIT ?
        """,
        (max(1, min(int(limit), 100)),),
    ).fetchall()


def _mark_event(
    conn: sqlite3.Connection,
    event_id: int,
    *,
    dm_sent: bool,
    public_sent: bool,
    attempts: int,
    error: str | None,
) -> None:
    if dm_sent and public_sent:
        conn.execute(
            """
            UPDATE offer_withdrawal_outbox
            SET dm_sent=1,
                public_sent=1,
                status='SENT',
                last_error=NULL,
                processed_at=CURRENT_TIMESTAMP
            WHERE id=? AND status='PENDING'
            """,
            (int(event_id),),
        )
    else:
        conn.execute(
            """
            UPDATE offer_withdrawal_outbox
            SET dm_sent=?,
                public_sent=?,
                attempts=?,
                last_error=?,
                next_attempt_at=datetime('now', '+30 seconds')
            WHERE id=? AND status='PENDING'
            """,
            (
                1 if dm_sent else 0,
                1 if public_sent else 0,
                int(attempts) + 1,
                str(error or "Notificación incompleta")[:500],
                int(event_id),
            ),
        )
    conn.commit()


async def sync_guild(guild) -> None:
    if APP is None or BOT is None:
        return

    conn = APP.db_for_guild(guild.id)
    try:
        conn.row_factory = sqlite3.Row
        events = [dict(row) for row in _pending_events(conn)]
        conn.commit()
    finally:
        conn.close()

    for event in events:
        event_id = int(event["id"])
        offer_id = int(event["offer_id"])
        dm_sent = bool(event["dm_sent"])
        public_sent = bool(event["public_sent"])
        attempts = int(event["attempts"] or 0)

        conn = APP.db_for_guild(guild.id)
        try:
            conn.row_factory = sqlite3.Row
            offer = conn.execute(
                "SELECT * FROM offers WHERE id=? LIMIT 1",
                (offer_id,),
            ).fetchone()
            if offer is None:
                conn.execute(
                    """
                    UPDATE offer_withdrawal_outbox
                    SET status='SKIPPED_MISSING',
                        last_error='La oferta ya no existe.',
                        processed_at=CURRENT_TIMESTAMP
                    WHERE id=? AND status='PENDING'
                    """,
                    (event_id,),
                )
                conn.commit()
                continue
            if str(offer["status"] or "").upper() != "RETIRADA":
                conn.execute(
                    """
                    UPDATE offer_withdrawal_outbox
                    SET status='SKIPPED_STATE',
                        last_error=?,
                        processed_at=CURRENT_TIMESTAMP
                    WHERE id=? AND status='PENDING'
                    """,
                    (f"Estado actual: {offer['status']}", event_id),
                )
                conn.commit()
                continue
            offer = dict(offer)
        finally:
            conn.close()

        errors = []

        if not dm_sent:
            try:
                seller = BOT.get_user(int(offer["to_id"]))
                if seller is None:
                    seller = await BOT.fetch_user(int(offer["to_id"]))
                await seller.send(embed=_withdrawal_embed(APP, offer))
                dm_sent = True
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
                errors.append(f"DM: {type(exc).__name__}: {exc}")

        if not public_sent:
            channel = await _resolve_market_channel(APP, BOT, guild)
            if channel is None:
                # If no market channel is configured there is no public surface
                # to mirror; treat that leg as intentionally complete.
                public_sent = True
            else:
                try:
                    await channel.send(
                        content=(
                            f"<@{int(offer['to_id'])}> ↩️ "
                            f"**{offer['from_club']} retiró su oferta por "
                            f"{offer['player']}.**"
                        ),
                        embed=_withdrawal_embed(APP, offer),
                        allowed_mentions=discord.AllowedMentions(
                            users=True,
                            roles=False,
                            everyone=False,
                        ),
                    )
                    public_sent = True
                except (discord.Forbidden, discord.HTTPException) as exc:
                    errors.append(f"Canal: {type(exc).__name__}: {exc}")

        conn = APP.db_for_guild(guild.id)
        try:
            conn.row_factory = sqlite3.Row
            _mark_event(
                conn,
                event_id,
                dm_sent=dm_sent,
                public_sent=public_sent,
                attempts=attempts,
                error=" | ".join(errors) if errors else None,
            )
        finally:
            conn.close()


def apply_offer_withdrawal_patch(runtime, bot) -> None:
    global APP, BOT
    if getattr(runtime, "_ajpa_offer_withdrawal_patch", False):
        return

    APP = runtime
    BOT = bot

    @tasks.loop(seconds=3)
    async def withdrawal_worker():
        if not bot.is_ready():
            return
        for guild in list(bot.guilds):
            try:
                await sync_guild(guild)
            except Exception as exc:
                print(
                    "AJPA retiro oferta worker error | "
                    f"guild={getattr(guild, 'id', '?')} | "
                    f"{type(exc).__name__}: {exc}"
                )

    async def on_ready():
        for guild in list(bot.guilds):
            try:
                conn = runtime.db_for_guild(guild.id)
                try:
                    conn.row_factory = sqlite3.Row
                    ensure_schema(conn)
                    conn.commit()
                finally:
                    conn.close()
                await sync_guild(guild)
            except Exception as exc:
                print(
                    "AJPA retiro oferta startup error | "
                    f"guild={getattr(guild, 'id', '?')} | "
                    f"{type(exc).__name__}: {exc}"
                )
        if not withdrawal_worker.is_running():
            withdrawal_worker.start()

    bot.add_listener(on_ready, "on_ready")
    runtime.withdraw_pending_offer = withdraw_offer
    runtime._ajpa_offer_withdrawal_patch = True
    runtime._ajpa_offer_withdrawal_worker = withdrawal_worker
    print("AJPA retiro de ofertas activo: App + Discord -> RETIRADA + avisos compartidos")
