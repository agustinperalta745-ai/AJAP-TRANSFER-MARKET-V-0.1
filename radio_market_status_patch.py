"""Radio Pasillo announcements for real manual market open/close transitions.

The competition stage never drives this feature. A post is queued only when the
persisted market_state actually changes through the Staff controls (Discord or
AJPA Mobile), and the bot delivers the matching transparent AJPA artwork to the
Radio Pasillo channel.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import discord
from discord.ext import tasks

import guild_isolation_patch as guild_isolation
import market_persistence_patch as market_persistence
import mobile_parity_api_patch as mobile_parity


APP = None
BOT = None

ROOT = Path(__file__).resolve().parent
MARKET_OPEN_IMAGE = ROOT / "assets" / "radio_market_open_ajpa.png"
MARKET_CLOSED_IMAGE = ROOT / "assets" / "radio_market_closed_ajpa.png"
RETRY_SECONDS = 60


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _ensure_outbox(conn: sqlite3.Connection) -> None:
    # Keep these statements transaction-friendly: callers may already be inside
    # the same transaction that changes market_state.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS radio_market_status_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            is_open INTEGER NOT NULL,
            changed_by INTEGER,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_error TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_radio_market_status_pending
        ON radio_market_status_outbox(status, next_attempt_at, id)
        """
    )


def queue_market_status_announcement(
    conn: sqlite3.Connection,
    opened: bool,
    *,
    changed_by: int | None,
    source: str,
) -> int:
    """Queue one Radio Pasillo image for one real state transition.

    The caller owns commit/rollback so mobile changes can queue atomically with
    market_state. Discord's legacy setter commits first and queues immediately
    afterward in the same guild database.
    """
    _ensure_outbox(conn)
    cur = conn.execute(
        """
        INSERT INTO radio_market_status_outbox
            (is_open, changed_by, source)
        VALUES (?, ?, ?)
        """,
        (
            1 if opened else 0,
            int(changed_by) if changed_by is not None else None,
            (str(source or "MANUAL").strip().upper() or "MANUAL")[:80],
        ),
    )
    return int(cur.lastrowid)


def _conn_for_guild(guild_id: int):
    if APP is None:
        raise RuntimeError("AJPA runtime todavía no inicializado")
    if hasattr(APP, "db_for_guild"):
        return APP.db_for_guild(int(guild_id))
    if hasattr(APP, "guild_context"):
        with APP.guild_context(int(guild_id)):
            return APP.db()
    return APP.db()


def _pending(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    conn.row_factory = sqlite3.Row
    _ensure_outbox(conn)
    conn.commit()
    rows = conn.execute(
        """
        SELECT id, is_open, changed_by, source, attempts
        FROM radio_market_status_outbox
        WHERE status='PENDING'
          AND datetime(next_attempt_at) <= datetime('now')
        ORDER BY id ASC
        LIMIT ?
        """,
        (max(1, min(int(limit), 100)),),
    ).fetchall()
    return [dict(row) for row in rows]


def _mark_sent(conn: sqlite3.Connection, event_id: int) -> None:
    conn.execute(
        """
        UPDATE radio_market_status_outbox
        SET status='PUBLISHED', processed_at=CURRENT_TIMESTAMP, last_error=NULL
        WHERE id=? AND status='PENDING'
        """,
        (int(event_id),),
    )
    conn.commit()


def _retry(conn: sqlite3.Connection, event_id: int, error: str) -> None:
    conn.execute(
        """
        UPDATE radio_market_status_outbox
        SET attempts=attempts+1,
            last_error=?,
            next_attempt_at=datetime('now', ?)
        WHERE id=? AND status='PENDING'
        """,
        (str(error)[:500], f"+{RETRY_SECONDS} seconds", int(event_id)),
    )
    conn.commit()


def _artwork(opened: bool) -> tuple[Path, str]:
    if opened:
        return MARKET_OPEN_IMAGE, "mercado_abierto.png"
    return MARKET_CLOSED_IMAGE, "mercado_cerrado.png"


async def _process_guild(guild) -> int:
    if guild is None:
        return 0

    # Radio Pasillo already owns channel discovery/configuration; reuse that
    # canonical resolver instead of creating a second channel setting.
    import radio_pasillo_feature_ads_patch as radio

    with closing(_conn_for_guild(guild.id)) as conn:
        events = _pending(conn)

    if not events:
        return 0

    channel = await radio._resolve_radio_channel(guild)
    if channel is None:
        with closing(_conn_for_guild(guild.id)) as conn:
            for event in events:
                _retry(conn, int(event["id"]), "Canal Radio Pasillo no encontrado")
        return 0

    published = 0
    for event in events:
        event_id = int(event["id"])
        opened = bool(event["is_open"])
        image_path, filename = _artwork(opened)
        if not image_path.exists():
            with closing(_conn_for_guild(guild.id)) as conn:
                _retry(conn, event_id, f"Falta asset {image_path.name}")
            continue

        try:
            # The artwork itself is the announcement; no extra generated card or
            # substitute image is used.
            await channel.send(file=discord.File(str(image_path), filename=filename))
        except (discord.Forbidden, discord.HTTPException, OSError) as exc:
            with closing(_conn_for_guild(guild.id)) as conn:
                _retry(conn, event_id, f"{type(exc).__name__}: {exc}")
            continue

        with closing(_conn_for_guild(guild.id)) as conn:
            _mark_sent(conn, event_id)
        published += 1
        print(
            "AJPA Radio Pasillo mercado anunciado | "
            f"guild={guild.id} state={'ABIERTO' if opened else 'CERRADO'} "
            f"source={event.get('source')}"
        )

    return published


@tasks.loop(seconds=5)
async def _market_status_loop():
    if BOT is None or not BOT.is_ready():
        return
    for guild in list(getattr(BOT, "guilds", [])):
        try:
            await _process_guild(guild)
        except Exception as exc:
            print(
                "WARNING AJPA Radio Pasillo market status | "
                f"guild={getattr(guild, 'id', None)} {type(exc).__name__}: {exc}"
            )


@_market_status_loop.before_loop
async def _before_market_status_loop():
    if BOT is not None:
        await BOT.wait_until_ready()


async def _on_ready_market_status():
    if BOT is None:
        return
    # Flush persisted events immediately after a restart, then keep the small
    # retry worker alive for transient Discord/channel failures.
    for guild in list(getattr(BOT, "guilds", [])):
        try:
            await _process_guild(guild)
        except Exception as exc:
            print(
                "WARNING AJPA Radio Pasillo startup market status | "
                f"guild={getattr(guild, 'id', None)} {type(exc).__name__}: {exc}"
            )
    if not _market_status_loop.is_running():
        _market_status_loop.start()


def apply_radio_market_status_patch(runtime, bot) -> None:
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajpa_radio_market_status_patch", False):
        return

    bot.add_listener(_on_ready_market_status, "on_ready")
    runtime._ajpa_radio_market_status_patch = True
    print(
        "AJPA Radio Pasillo: anuncios ABIERTO/CERRADO conectados al estado manual real"
    )


# --- Discord Staff market control -------------------------------------------------
# market_persistence_patch is imported by run_bot after bot.py loaded this module.
# Wrap its installer now so the runtime setter queues only genuine transitions.
_original_install_persistent_state = market_persistence.install_persistent_state


def _install_persistent_state_with_radio(runtime):
    _original_install_persistent_state(runtime)
    base_change = runtime.cambiar_estado_mercado
    if getattr(base_change, "_ajpa_radio_market_status_wrapped", False):
        return

    def cambiar_estado_mercado(abierto: bool, admin_id: int):
        before = bool(runtime.mercado_abierto())
        result = base_change(abierto, admin_id)
        after = bool(result)
        if before != after:
            try:
                with runtime.db() as conn:
                    queue_market_status_announcement(
                        conn,
                        after,
                        changed_by=int(admin_id),
                        source="DISCORD_STAFF",
                    )
            except Exception as exc:
                # Never roll back a market state that already committed; surface
                # the queue failure loudly so the operator can inspect Railway.
                print(
                    "WARNING AJPA Radio Pasillo queue (Discord) | "
                    f"{type(exc).__name__}: {exc}"
                )
        return result

    cambiar_estado_mercado._ajpa_radio_market_status_wrapped = True
    runtime.cambiar_estado_mercado = cambiar_estado_mercado


market_persistence.install_persistent_state = _install_persistent_state_with_radio


# --- AJPA Mobile Staff market control --------------------------------------------
# Mobile's setter does not commit on its own, so its announcement row is queued
# in the same transaction as market_state/history.
_original_mobile_set_market_state = mobile_parity.set_market_state


def _mobile_set_market_state_with_radio(conn, session: dict, opened: bool) -> dict:
    old = False
    if _table_exists(conn, "market_state"):
        row = conn.execute("SELECT is_open FROM market_state WHERE id=1 LIMIT 1").fetchone()
        if row is not None:
            try:
                old = bool(int(row["is_open"]))
            except (TypeError, KeyError, IndexError):
                old = bool(int(row[0]))

    result = _original_mobile_set_market_state(conn, session, opened)
    current = bool(result.get("market_open"))
    if old != current:
        queue_market_status_announcement(
            conn,
            current,
            changed_by=int(session["user_id"]),
            source="MOBILE_STAFF",
        )
    return result


mobile_parity.set_market_state = _mobile_set_market_state_with_radio


# Receive runtime/bot through the same guild-isolation startup chain used by the
# rest of AJPA. Competition stage changes are intentionally not hooked here.
_base_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_market_status(runtime, bot):
    _base_apply_guild_isolation_patch(runtime, bot)
    apply_radio_market_status_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_radio_market_status_wrapped",
    False,
):
    _apply_guild_isolation_then_market_status._ajpa_radio_market_status_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_market_status
