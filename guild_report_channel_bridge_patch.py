"""Bridge per-guild Staff/PES channel lookups for background Liga listeners.

Slash commands/buttons run inside guild_isolation's ContextVar, but Discord
on_message listeners do not. /canal_movimientos was therefore written to the
correct guild DB while Liga review lookups could fall back to the legacy DB.
This patch makes report-channel reads/writes explicit by guild_id and serializes
manual-review creation so one source message cannot emit duplicate review cards.
"""

from __future__ import annotations

import asyncio

import market_channel_report_patch as market_reports
import league_validation_admin_review_patch as strict


_REVIEW_LOCKS: dict[int, asyncio.Lock] = {}


def _runtime():
    return market_reports.APP or strict.APP


def _conn_for_guild(guild_id: int):
    runtime = _runtime()
    if runtime is None:
        raise RuntimeError("AJAP runtime todavía no inicializado")
    if hasattr(runtime, "db_for_guild"):
        return runtime.db_for_guild(int(guild_id))
    if hasattr(runtime, "guild_context"):
        with runtime.guild_context(int(guild_id)):
            return runtime.db()
    return runtime.db()


def _ensure_report_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_report_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            configured_by INTEGER,
            configured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def get_report_channel_id_for_guild(guild_id: int):
    conn = _conn_for_guild(int(guild_id))
    try:
        _ensure_report_table(conn)
        row = conn.execute(
            "SELECT channel_id FROM market_report_channels WHERE guild_id = ? LIMIT 1",
            (int(guild_id),),
        ).fetchone()
        return int(row["channel_id"]) if row else None
    finally:
        conn.close()


def set_report_channel_for_guild(guild_id: int, channel_id: int, user_id: int):
    conn = _conn_for_guild(int(guild_id))
    try:
        _ensure_report_table(conn)
        conn.execute(
            """
            INSERT INTO market_report_channels
                (guild_id, channel_id, configured_by, configured_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id=excluded.channel_id,
                configured_by=excluded.configured_by,
                updated_at=CURRENT_TIMESTAMP
            """,
            (int(guild_id), int(channel_id), int(user_id)),
        )
        conn.commit()
    finally:
        conn.close()


# Functions inside market_channel_report_patch resolve these names at call time,
# so replacing the module globals also fixes resolve_channel() and every caller.
market_reports.get_report_channel_id = get_report_channel_id_for_guild
market_reports.set_report_channel = set_report_channel_for_guild


_original_send_admin_review = strict._send_admin_review


async def _send_admin_review_once(message, reason: str, hashes=None):
    lock = _REVIEW_LOCKS.setdefault(int(message.id), asyncio.Lock())
    async with lock:
        return await _original_send_admin_review(message, reason, hashes)


strict._send_admin_review = _send_admin_review_once

# Import side effect: monta el resumen público encima del aislamiento por guild.
# Este módulo se carga desde bot.py antes de run_bot, por lo que el wrapper queda
# instalado antes de que Discord conecte.
import public_market_summary_patch  # noqa: F401,E402
# Cada oferta válida agrega un rumor breve estilo prensa al mismo resumen público,
# sin exponer monto ni condiciones de la negociación.
import market_rumor_patch  # noqa: F401,E402

print("AJAP bridge Staff/PES activo: canal por guild explícito + revisión sin duplicados")
