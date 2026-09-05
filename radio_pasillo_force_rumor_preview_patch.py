"""One-shot Radio Pasillo rumor preview requested by AJPA staff.

On the next bot ready event, send exactly one rumor in the configured Discord
guild, ignoring the normal two-hour cooldown only for this preview. A persistent
DB marker prevents reconnects/restarts from sending it again.
"""
from __future__ import annotations

import os
import random
import time
from contextlib import closing

import discord

import radio_pasillo_feature_ads_patch as radio
import radio_pasillo_game_rumors_patch as rumors


PREVIEW_KEY = "rumor-preview-2026-09-05-v1"
_REGISTERED_BOTS = set()


def _ensure_preview_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS radio_pasillo_preview_state (
            guild_id INTEGER NOT NULL,
            preview_key TEXT NOT NULL,
            sent_at INTEGER NOT NULL,
            discord_message_id INTEGER,
            PRIMARY KEY (guild_id, preview_key)
        )
        """
    )
    conn.commit()


def _already_sent(conn, guild_id: int) -> bool:
    _ensure_preview_schema(conn)
    row = conn.execute(
        """
        SELECT 1
        FROM radio_pasillo_preview_state
        WHERE guild_id=? AND preview_key=?
        LIMIT 1
        """,
        (int(guild_id), PREVIEW_KEY),
    ).fetchone()
    return bool(row)


def _mark_preview_sent(conn, guild_id: int, message_id: int) -> None:
    _ensure_preview_schema(conn)
    conn.execute(
        """
        INSERT OR IGNORE INTO radio_pasillo_preview_state
            (guild_id, preview_key, sent_at, discord_message_id)
        VALUES (?, ?, ?, ?)
        """,
        (int(guild_id), PREVIEW_KEY, int(time.time()), int(message_id)),
    )
    conn.commit()


def _target_guild(bot):
    configured = (os.getenv("DISCORD_GUILD_ID") or "").strip()
    if configured.isdigit():
        guild = bot.get_guild(int(configured))
        if guild is not None:
            return guild

    guilds = list(getattr(bot, "guilds", []) or [])
    return guilds[0] if len(guilds) == 1 else None


async def _send_preview_once(bot) -> bool:
    guild = _target_guild(bot)
    if guild is None:
        print("AJAP Radio Pasillo preview: guild objetivo no encontrado")
        return False

    with closing(radio._conn_for_guild(guild.id)) as conn:
        if _already_sent(conn, guild.id):
            return False
        row = radio._state(conn, guild.id)
        last_key = str(row["last_ad_key"]) if row and row["last_ad_key"] else None

    candidates = rumors._rumor_candidates(guild.id, last_key)
    if not candidates:
        print(f"AJAP Radio Pasillo preview: no hay rumores elegibles guild={guild.id}")
        return False

    channel = await radio._resolve_radio_channel(guild)
    role = radio._dt_role(guild)
    if channel is None or role is None:
        print(
            "AJAP Radio Pasillo preview: falta canal o rol DT "
            f"guild={guild.id} channel={getattr(channel, 'id', None)} role={getattr(role, 'id', None)}"
        )
        return False

    message_key, body = random.choice(candidates)
    content = f"{role.mention}\n📣 **RADIO PASILLO • RUMORES**\n{body}"

    try:
        sent = await channel.send(
            content=content,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=True,
                replied_user=False,
            ),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            "AJAP Radio Pasillo preview: envío falló "
            f"guild={guild.id} error={type(exc).__name__}: {exc}"
        )
        return False

    now = int(time.time())
    with closing(radio._conn_for_guild(guild.id)) as conn:
        _mark_preview_sent(conn, guild.id, sent.id)
        # La prueba cuenta como publicación de Radio Pasillo para no mandar otra
        # automática inmediatamente después.
        radio._mark_sent(
            conn,
            guild.id,
            now=now,
            ad_key=message_key,
            channel_id=channel.id,
            message_id=sent.id,
        )

    print(
        "AJAP Radio Pasillo preview enviado "
        f"guild={guild.id} channel={channel.id} key={message_key}"
    )
    return True


async def _on_ready_force_rumor_preview():
    bot = radio.BOT
    if bot is None or not bot.is_ready():
        return
    try:
        await _send_preview_once(bot)
    except Exception as exc:
        print(
            "AJAP Radio Pasillo preview: error inesperado "
            f"{type(exc).__name__}: {exc}"
        )


def _register(bot) -> None:
    if bot is None:
        return
    marker = id(bot)
    if marker in _REGISTERED_BOTS:
        return
    bot.add_listener(_on_ready_force_rumor_preview, "on_ready")
    _REGISTERED_BOTS.add(marker)
    print("AJAP Radio Pasillo: preview único de rumor preparado")


# Soporta ambos órdenes de carga: si Radio Pasillo ya fue aplicado, registra el
# listener ahora; si todavía no, envuelve su apply para registrarlo después.
if radio.BOT is not None:
    _register(radio.BOT)

_BASE_APPLY = radio.apply_radio_pasillo_feature_ads_patch


def _apply_radio_then_preview(runtime, bot):
    _BASE_APPLY(runtime, bot)
    _register(bot)


if not getattr(
    radio.apply_radio_pasillo_feature_ads_patch,
    "_ajap_force_rumor_preview_wrapped",
    False,
):
    _apply_radio_then_preview._ajap_force_rumor_preview_wrapped = True
    radio.apply_radio_pasillo_feature_ads_patch = _apply_radio_then_preview
