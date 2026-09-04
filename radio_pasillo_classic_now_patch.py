"""One-time Radio Pasillo push requested by AJPA staff.

On the next successful bot start, publish the classic-rival reminder immediately
once per guild, then continue the normal two-hour rotation from that point.
Also pins the real AJPA Mobile MediaFire URL into the existing ad rotation so it
does not depend on a Railway environment variable.
"""

from __future__ import annotations

import time
from contextlib import closing

import discord

import guild_isolation_patch as guild_isolation
import radio_pasillo_feature_ads_patch as ads


APP_DOWNLOAD_URL = "https://www.mediafire.com/file/m13t4jblgeb473c/AJPA-Transfer-Market-Actualizador.apk/file"
PUSH_KEY = "classic-now-2026-09-04-v1"

# The regular rotation reads this module global dynamically in _eligible_ads().
ads.APP_DOWNLOAD_URL = APP_DOWNLOAD_URL


def _classic_body() -> str:
    for key, body in ads._ADS:
        if key == "classic":
            return body
    return (
        "🔥 **¿Ya definiste tu clásico rival?**\n"
        "Entrá a `/mercado` → **MI CLUB** → **CLÁSICO RIVAL**, elegí al rival y enviá la propuesta. "
        "El otro DT tiene que aceptarla y el historial queda registrado."
    )


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
        # Make this forced message the start of the normal 2-hour cadence.
        ads._mark_sent(
            conn,
            int(guild_id),
            now=int(now),
            ad_key="classic",
            channel_id=int(channel_id),
            message_id=int(message_id),
        )
        conn.commit()


async def _send_classic_once(guild) -> bool:
    if guild is None or _already_sent(guild.id):
        return False

    channel = await ads._resolve_radio_channel(guild)
    role = ads._dt_role(guild)
    if channel is None or role is None:
        print(
            "AJAP classic reminder one-shot pendiente "
            f"guild={getattr(guild, 'id', None)} channel={getattr(channel, 'id', None)} role={getattr(role, 'id', None)}"
        )
        return False

    content = (
        f"{role.mention}\n"
        "📻 **RADIO PASILLO • RECORDATORIO AJPA**\n"
        f"{_classic_body()}"
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
            "AJAP classic reminder one-shot falló "
            f"guild={guild.id} error={type(exc).__name__}: {exc}"
        )
        return False

    now = int(time.time())
    _mark_manual(guild.id, channel.id, sent.id, now)
    print(
        "AJAP classic reminder one-shot enviado "
        f"guild={guild.id} channel={channel.id} message={sent.id}"
    )
    return True


async def _on_ready_classic_push():
    bot = ads.BOT
    if bot is None:
        return
    for guild in list(getattr(bot, "guilds", [])):
        try:
            await _send_classic_once(guild)
        except Exception as exc:
            print(
                "AJAP classic reminder one-shot error "
                f"guild={getattr(guild, 'id', None)} error={type(exc).__name__}: {exc}"
            )


def apply_classic_now_patch(runtime, bot) -> None:
    if getattr(runtime, "_ajap_classic_now_patch", False):
        return
    # Reassert the URL after runtime setup in case an older environment value exists.
    ads.APP_DOWNLOAD_URL = APP_DOWNLOAD_URL
    bot.add_listener(_on_ready_classic_push, "on_ready")
    runtime._ajap_classic_now_patch = True
    print("AJAP Radio Pasillo: clásico inmediato one-shot listo + MediaFire fijo")


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
