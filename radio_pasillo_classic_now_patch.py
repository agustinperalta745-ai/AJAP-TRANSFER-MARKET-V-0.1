"""Radio Pasillo cadence override + one-time AJPA Mobile push.

On the next successful bot start, publish the AJPA Mobile download reminder
immediately once per guild. From that message onward, the regular rotating
Radio Pasillo reminders run every 40 minutes. State remains persisted per guild
so Railway reconnects/restarts do not duplicate the one-shot.
"""

from __future__ import annotations

import time
from contextlib import closing

import discord

import guild_isolation_patch as guild_isolation
import radio_pasillo_feature_ads_patch as ads


APP_DOWNLOAD_URL = "https://www.mediafire.com/file/m13t4jblgeb473c/AJPA-Transfer-Market-Actualizador.apk/file"
PUSH_KEY = "app-now-2026-09-04-v1"
INTERVAL_MINUTES = 40


def _app_body() -> str:
    return ads._APP_AD[1].format(url=APP_DOWNLOAD_URL)


def _already_sent(guild_id: int) -> bool:
    with closing(ads._conn_for_guild(guild_id)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radio_pasillo_manual_pushes (
                push_key TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                sent_at INTEGER NOT NULL,
                channel_id INTEGER,
                discord_message_id INTEGER,
                PRIMARY KEY (push_key, guild_id)
            )
            """
        )
        row = conn.execute(
            "SELECT 1 FROM radio_pasillo_manual_pushes WHERE push_key=? AND guild_id=? LIMIT 1",
            (PUSH_KEY, int(guild_id)),
        ).fetchone()
        conn.commit()
        return bool(row)


def _mark_manual(guild_id: int, channel_id: int, message_id: int, now: int) -> None:
    with closing(ads._conn_for_guild(guild_id)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radio_pasillo_manual_pushes (
                push_key TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                sent_at INTEGER NOT NULL,
                channel_id INTEGER,
                discord_message_id INTEGER,
                PRIMARY KEY (push_key, guild_id)
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO radio_pasillo_manual_pushes
                (push_key, guild_id, sent_at, channel_id, discord_message_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (PUSH_KEY, int(guild_id), int(now), int(channel_id), int(message_id)),
        )
        # The forced app message becomes the start of the new 40-minute cadence.
        ads._mark_sent(
            conn,
            int(guild_id),
            now=int(now),
            ad_key="app",
            channel_id=int(channel_id),
            message_id=int(message_id),
        )
        conn.commit()


async def _send_app_once(guild) -> bool:
    if guild is None or _already_sent(guild.id):
        return False

    channel = await ads._resolve_radio_channel(guild)
    role = ads._dt_role(guild)
    if channel is None or role is None:
        print(
            "AJAP app reminder one-shot pendiente "
            f"guild={getattr(guild, 'id', None)} channel={getattr(channel, 'id', None)} role={getattr(role, 'id', None)}"
        )
        return False

    content = (
        f"{role.mention}\n"
        "📻 **RADIO PASILLO • RECORDATORIO AJPA**\n"
        f"{_app_body()}"
    )
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
            "AJAP app reminder one-shot falló "
            f"guild={guild.id} error={type(exc).__name__}: {exc}"
        )
        return False

    now = int(time.time())
    _mark_manual(guild.id, channel.id, sent.id, now)
    print(
        "AJAP app reminder one-shot enviado "
        f"guild={guild.id} channel={channel.id} message={sent.id}"
    )
    return True


async def _on_ready_app_push():
    bot = ads.BOT
    if bot is None:
        return
    for guild in list(getattr(bot, "guilds", [])):
        try:
            await _send_app_once(guild)
        except Exception as exc:
            print(
                "AJAP app reminder one-shot error "
                f"guild={getattr(guild, 'id', None)} error={type(exc).__name__}: {exc}"
            )


def apply_classic_now_patch(runtime, bot) -> None:
    if getattr(runtime, "_ajap_classic_now_patch", False):
        return

    # The base Radio Pasillo patch is already installed at this point. Override
    # its due-time gate and tighten its checker so a reminder lands on the
    # 40-minute cadence instead of waiting on a coarse poll.
    ads.APP_DOWNLOAD_URL = APP_DOWNLOAD_URL
    ads.INTERVAL_SECONDS = INTERVAL_MINUTES * 60
    try:
        ads._ad_loop.change_interval(minutes=1)
    except Exception as exc:
        print(f"WARNING AJAP: no se pudo ajustar el chequeo de Radio Pasillo a 1 min: {exc}")

    # Prevent the normal loop from racing the requested immediate app message on
    # startup. Until this PUSH_KEY exists for the guild, only the one-shot may
    # publish; afterwards the normal rotation resumes from that app timestamp.
    original_send_due = ads._send_due

    async def _send_due_after_app(guild):
        if guild is not None and not _already_sent(guild.id):
            return False
        return await original_send_due(guild)

    ads._send_due = _send_due_after_app
    runtime.radio_pasillo_send_feature_ad_if_due = _send_due_after_app

    bot.add_listener(_on_ready_app_push, "on_ready")
    runtime._ajap_classic_now_patch = True
    print(
        f"AJAP Radio Pasillo: rotación cada {INTERVAL_MINUTES} min + AJPA Mobile inmediato one-shot"
    )


_base_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_classic_now(runtime, bot):
    _base_apply_guild_isolation_patch(runtime, bot)
    apply_classic_now_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_classic_now_wrapped",
    False,
):
    _apply_guild_isolation_then_classic_now._ajap_classic_now_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_classic_now


# Public utility commands are loaded here, immediately before run_bot starts.
# The module hooks the final guild-isolation installer and registers /dado on
# the real runtime bot without touching Radio Pasillo state.
import dice_challenge_patch  # noqa: F401,E402
# Final command-registry repair: create a fresh guild-scoped /dado after every
# ready event so Discord mobile receives the slash suggestion immediately.
import dice_guild_sync_fix_patch  # noqa: F401,E402
