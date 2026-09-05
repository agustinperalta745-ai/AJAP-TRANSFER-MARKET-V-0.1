"""One-shot Radio Pasillo rumor preview requested by AJPA staff.

Preview v2 is deliberately independent from the normal two-hour cooldown. It
walks every guild where this bot is actually connected, resolves Radio Pasillo
and the DT role, builds a rumor from a real player belonging to a club with a
linked DT, and marks the preview only after Discord returns a message id.

If startup order or roster aliases temporarily prevent the first attempt, a
short bounded retry runs after on_ready. Reconnects remain safe because the
persistent per-guild preview marker is written only after a successful send.
"""
from __future__ import annotations

import asyncio
import random
import time
from contextlib import closing, nullcontext

import discord

import radio_pasillo_feature_ads_patch as radio
import radio_pasillo_game_rumors_patch as rumors
import radio_pasillo_sports_column_patch as sports


PREVIEW_KEY = "rumor-preview-2026-09-05-v2"
_REGISTERED_BOTS = set()
_RUNNING_BOTS = set()


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
        SELECT discord_message_id
        FROM radio_pasillo_preview_state
        WHERE guild_id=? AND preview_key=?
        LIMIT 1
        """,
        (int(guild_id), PREVIEW_KEY),
    ).fetchone()
    return bool(row and row["discord_message_id"])


def _mark_preview_sent(conn, guild_id: int, message_id: int) -> None:
    _ensure_preview_schema(conn)
    conn.execute(
        """
        INSERT INTO radio_pasillo_preview_state
            (guild_id, preview_key, sent_at, discord_message_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, preview_key) DO UPDATE SET
            sent_at=excluded.sent_at,
            discord_message_id=excluded.discord_message_id
        """,
        (int(guild_id), PREVIEW_KEY, int(time.time()), int(message_id)),
    )
    conn.commit()


def _extract_player_name(item):
    if isinstance(item, dict):
        value = item.get("name") or item.get("player")
    else:
        try:
            value = item["name"]
        except Exception:
            value = getattr(item, "name", None)
    value = str(value or "").strip()
    return value or None


def _runtime_roster(guild_id: int, team: str):
    app = radio.APP
    if app is None or not hasattr(app, "jugadores_de_club"):
        return []

    ctx = nullcontext()
    if hasattr(app, "guild_context"):
        try:
            ctx = app.guild_context(int(guild_id))
        except Exception:
            ctx = nullcontext()

    try:
        with ctx:
            rows = app.jugadores_de_club(team, 100) or []
    except Exception:
        return []

    output = []
    for item in rows:
        name = _extract_player_name(item)
        if name:
            output.append(name)
    return output


def _linked_player_pool(guild_id: int):
    """Return (team, player) pairs, using both DB and the bot's normal roster API."""
    try:
        with closing(radio._conn_for_guild(guild_id)) as conn:
            linked = sports._linked_clubs(conn)
            if not linked:
                return []

            pool = []
            seen = set()
            for linked_name in linked:
                variants = []
                for value in (linked_name, sports._canonical_team(linked_name)):
                    value = str(value or "").strip()
                    if value and value not in variants:
                        variants.append(value)

                roster_names = []
                for variant in variants:
                    roster_names.extend(sports._team_roster(conn, variant))

                # Some historical teams use an alias in clubs while the live
                # roster helper knows the active/canonical name. Use it as a
                # fallback so a valid linked club never disappears due to aliasing.
                if not roster_names:
                    for variant in variants:
                        roster_names.extend(_runtime_roster(guild_id, variant))

                team = sports._canonical_team(linked_name) or linked_name
                for player in roster_names:
                    player = str(player or "").strip()
                    if not player:
                        continue
                    key = (sports._team_key(team), sports._norm(player))
                    if key in seen:
                        continue
                    seen.add(key)
                    pool.append((str(team), player))
            return pool
    except Exception as exc:
        print(
            "AJAP Radio Pasillo preview v2: no se pudo construir pool "
            f"guild={guild_id} error={type(exc).__name__}: {exc}"
        )
        return []


def _preview_candidates(guild_id: int, last_key: str | None):
    pool = _linked_player_pool(guild_id)
    if not pool:
        return []

    templates = list(
        rumors._POSITIVE_RUMORS
        + rumors._NEGATIVE_RUMORS
        + rumors._NEUTRAL_RUMORS
    )
    random.shuffle(pool)
    random.shuffle(templates)

    candidates = []
    for team, player in pool:
        for slug, template in templates:
            key = rumors._rumor_key(team, player, slug)
            if key == last_key:
                continue
            candidates.append((key, template.format(player=player, team=team)))
    return candidates


async def _send_preview_once(guild) -> str:
    """Return sent/already/retry. Never mark success before channel.send succeeds."""
    if guild is None:
        return "retry"

    with closing(radio._conn_for_guild(guild.id)) as conn:
        if _already_sent(conn, guild.id):
            return "already"
        row = radio._state(conn, guild.id)
        last_key = str(row["last_ad_key"]) if row and row["last_ad_key"] else None

    channel = await radio._resolve_radio_channel(guild)
    role = radio._dt_role(guild)
    if channel is None or role is None:
        print(
            "AJAP Radio Pasillo preview v2: falta canal o rol DT "
            f"guild={guild.id} channel={getattr(channel, 'id', None)} "
            f"role={getattr(role, 'id', None)}"
        )
        return "retry"

    candidates = _preview_candidates(guild.id, last_key)
    if not candidates:
        print(
            "AJAP Radio Pasillo preview v2: no hay jugadores elegibles "
            f"en clubes con DT guild={guild.id}"
        )
        return "retry"

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
            "AJAP Radio Pasillo preview v2: envío falló "
            f"guild={guild.id} channel={getattr(channel, 'id', None)} "
            f"error={type(exc).__name__}: {exc}"
        )
        return "retry"

    now = int(time.time())
    with closing(radio._conn_for_guild(guild.id)) as conn:
        _mark_preview_sent(conn, guild.id, sent.id)
        radio._mark_sent(
            conn,
            guild.id,
            now=now,
            ad_key=message_key,
            channel_id=channel.id,
            message_id=sent.id,
        )

    print(
        "AJAP Radio Pasillo preview v2 ENVIADO "
        f"guild={guild.id} channel={channel.id} message={sent.id} key={message_key}"
    )
    return "sent"


async def _run_preview_retries(bot) -> None:
    marker = id(bot)
    if marker in _RUNNING_BOTS:
        return
    _RUNNING_BOTS.add(marker)
    try:
        # Enough to survive normal startup ordering without turning this into a
        # permanent background loop. The DB marker guarantees one successful
        # preview maximum per guild for this preview version.
        for attempt in range(1, 13):
            guilds = list(getattr(bot, "guilds", []) or [])
            pending = False
            for guild in guilds:
                try:
                    result = await _send_preview_once(guild)
                except Exception as exc:
                    print(
                        "AJAP Radio Pasillo preview v2: error inesperado "
                        f"guild={getattr(guild, 'id', None)} "
                        f"error={type(exc).__name__}: {exc}"
                    )
                    result = "retry"
                if result == "retry":
                    pending = True

            if guilds and not pending:
                return
            if attempt < 12:
                await asyncio.sleep(10)
    finally:
        _RUNNING_BOTS.discard(marker)


async def _on_ready_force_rumor_preview():
    bot = radio.BOT
    if bot is None:
        return
    await _run_preview_retries(bot)


def register_force_rumor_preview(runtime, bot) -> None:
    """Explicit startup hook; safe to call repeatedly."""
    if bot is None:
        return
    marker = id(bot)
    if marker not in _REGISTERED_BOTS:
        bot.add_listener(_on_ready_force_rumor_preview, "on_ready")
        _REGISTERED_BOTS.add(marker)
        print("AJAP Radio Pasillo: preview v2 de rumor registrado")

    # Covers the rare case where another patch registers this after on_ready.
    try:
        if bot.is_ready():
            asyncio.create_task(_run_preview_retries(bot))
    except Exception:
        pass


# Keep compatibility with the existing Radio Pasillo startup chain. An explicit
# call from sitecustomize is also installed below in the main startup path.
if radio.BOT is not None:
    register_force_rumor_preview(radio.APP, radio.BOT)

_BASE_APPLY = radio.apply_radio_pasillo_feature_ads_patch


def _apply_radio_then_preview(runtime, bot):
    _BASE_APPLY(runtime, bot)
    register_force_rumor_preview(runtime, bot)


if not getattr(
    radio.apply_radio_pasillo_feature_ads_patch,
    "_ajap_force_rumor_preview_v2_wrapped",
    False,
):
    _apply_radio_then_preview._ajap_force_rumor_preview_v2_wrapped = True
    radio.apply_radio_pasillo_feature_ads_patch = _apply_radio_then_preview
