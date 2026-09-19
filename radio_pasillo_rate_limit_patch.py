"""Global 90-minute throttle for every AJPA Radio Pasillo post.

All bot-originated messages sent to the canonical Radio Pasillo text channel
share one per-guild slot. Calls wait asynchronously for their turn, so Discord
continues running while queued announcements are spaced out.

The last successful send is persisted in the guild database. If Railway
restarts while an announcement is waiting, the original event remains pending
because channel.send() has not returned yet; its normal recovery path can retry
it after reconnect.
"""

from __future__ import annotations

import asyncio
import time
import unicodedata
from contextlib import closing

import discord

import radio_pasillo_feature_ads_patch as radio


INTERVAL_SECONDS = 90 * 60

_ORIGINAL_SEND = None
_LOCKS: dict[int, asyncio.Lock] = {}
_MEMORY_LAST_SENT: dict[int, int] = {}


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _is_radio_pasillo_channel(channel) -> bool:
    guild = getattr(channel, "guild", None)
    if guild is None:
        return False
    return "radiopasillo" in _norm(getattr(channel, "name", ""))


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS radio_pasillo_global_throttle_state (
            guild_id INTEGER PRIMARY KEY,
            last_sent_at INTEGER NOT NULL DEFAULT 0,
            channel_id INTEGER,
            discord_message_id INTEGER,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _read_last_sent(guild_id: int) -> int:
    memory_value = int(_MEMORY_LAST_SENT.get(int(guild_id), 0) or 0)
    try:
        with closing(radio._conn_for_guild(int(guild_id))) as conn:
            _ensure_schema(conn)
            row = conn.execute(
                """
                SELECT last_sent_at
                FROM radio_pasillo_global_throttle_state
                WHERE guild_id=?
                LIMIT 1
                """,
                (int(guild_id),),
            ).fetchone()
            persisted = int(row["last_sent_at"]) if row and row["last_sent_at"] else 0
            return max(memory_value, persisted)
    except Exception as exc:
        print(
            "WARNING AJPA Radio Pasillo throttle: no se pudo leer estado "
            f"guild={guild_id}: {type(exc).__name__}: {exc}"
        )
        return memory_value


def _mark_sent(guild_id: int, channel_id: int, message_id: int, now: int) -> None:
    _MEMORY_LAST_SENT[int(guild_id)] = int(now)
    try:
        with closing(radio._conn_for_guild(int(guild_id))) as conn:
            _ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO radio_pasillo_global_throttle_state
                    (guild_id, last_sent_at, channel_id, discord_message_id, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id) DO UPDATE SET
                    last_sent_at=excluded.last_sent_at,
                    channel_id=excluded.channel_id,
                    discord_message_id=excluded.discord_message_id,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    int(guild_id),
                    int(now),
                    int(channel_id),
                    int(message_id),
                ),
            )
            conn.commit()
    except Exception as exc:
        print(
            "WARNING AJPA Radio Pasillo throttle: no se pudo persistir estado "
            f"guild={guild_id}: {type(exc).__name__}: {exc}"
        )


async def _wait_until_due(guild_id: int) -> None:
    while True:
        now = int(time.time())
        last_sent_at = _read_last_sent(int(guild_id))
        remaining = INTERVAL_SECONDS - (now - last_sent_at)
        if not last_sent_at or remaining <= 0:
            return

        print(
            "AJPA Radio Pasillo throttle: anuncio en espera "
            f"guild={guild_id} remaining={remaining}s"
        )
        await asyncio.sleep(max(1, int(remaining)))


def apply_radio_pasillo_rate_limit_patch(runtime, bot) -> None:
    global _ORIGINAL_SEND

    if getattr(bot, "_ajap_radio_pasillo_rate_limit_patch", False):
        return

    messageable = discord.abc.Messageable
    current_send = messageable.send
    if getattr(current_send, "_ajap_radio_pasillo_rate_limited", False):
        bot._ajap_radio_pasillo_rate_limit_patch = True
        return

    _ORIGINAL_SEND = current_send

    async def send_with_radio_pasillo_throttle(self, *args, **kwargs):
        if not _is_radio_pasillo_channel(self):
            return await _ORIGINAL_SEND(self, *args, **kwargs)

        guild = getattr(self, "guild", None)
        guild_id = int(getattr(guild, "id", 0) or 0)
        if not guild_id:
            return await _ORIGINAL_SEND(self, *args, **kwargs)

        lock = _LOCKS.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            _LOCKS[guild_id] = lock

        async with lock:
            await _wait_until_due(guild_id)
            sent = await _ORIGINAL_SEND(self, *args, **kwargs)
            now = int(time.time())
            _mark_sent(
                guild_id,
                int(getattr(self, "id", 0) or 0),
                int(getattr(sent, "id", 0) or 0),
                now,
            )
            print(
                "AJPA Radio Pasillo throttle: anuncio enviado "
                f"guild={guild_id} next_slot_in={INTERVAL_SECONDS}s"
            )
            return sent

    send_with_radio_pasillo_throttle._ajap_radio_pasillo_rate_limited = True
    messageable.send = send_with_radio_pasillo_throttle
    bot._ajap_radio_pasillo_rate_limit_patch = True

    print(
        "AJPA Radio Pasillo: límite global activo — máximo 1 anuncio cada 1h 30m por servidor"
    )
