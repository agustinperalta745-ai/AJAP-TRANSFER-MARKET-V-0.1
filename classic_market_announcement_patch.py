"""Publish committed classic confirmations to the existing public market feed."""

import asyncio
from contextlib import closing

import discord
from discord.ext import tasks

import market_rumor_patch as rumors
import mobile_classic_rival_api_patch as classic
import public_market_summary_patch as summary

KIND = "CLASSIC_CONFIRMED"
_locks = {}


def _club_emoji(guild, club):
    """Return this guild's manual team emoji, with canonical alias fallback."""
    try:
        import team_badge_selector_patch as selector
        import team_badges_patch as badges

        raw = str(club or "").strip()
        candidates = [raw]
        canonical = badges.ALIASES.get(raw.casefold())
        if canonical and canonical.casefold() != raw.casefold():
            candidates.append(canonical)
        for candidate in candidates:
            emoji = selector._find_badge_emoji(guild, candidate)
            if emoji is not None:
                return str(emoji)
    except Exception:
        # The announcement must still go out if an emoji is missing/unavailable.
        pass
    return "⚽"


def _manager_id(conn, club):
    try:
        return classic._owner_id(conn, str(club))
    except Exception:
        return None


def _mention(user_id):
    return f"<@{int(user_id)}>" if user_id else "Sin DT asignado"


def _allowed_mentions():
    # Ping only the two DT users. Never allow role/@everyone pings from this feed.
    return discord.AllowedMentions(
        everyone=False,
        roles=False,
        users=True,
        replied_user=False,
    )


async def publish_pending(guild):
    # Serialize overlapping reconnect/poll callbacks for the same guild.
    async with _locks.setdefault(int(guild.id), asyncio.Lock()):
        with closing(summary._conn_for_guild(guild.id)) as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='classic_market_outbox'"
            ).fetchone()
            if not exists:
                return
            rows = conn.execute(
                """SELECT c.id, c.club_a, c.club_b
                   FROM classic_market_outbox o
                   JOIN classic_rivals c ON c.id=o.classic_id
                   JOIN classic_rival_requests r ON r.id=c.accepted_request_id
                   WHERE r.status='ACCEPTED'
                   ORDER BY c.id LIMIT 25"""
            ).fetchall()

        for row in rows:
            classic_id = int(row["id"])
            if not summary._was_announced(guild.id, KIND, classic_id):
                channel, _source = await rumors._resolve_summary_channel(guild)
                if channel is None:
                    return  # Keep queued until the channel becomes available.

                raw_club_a = str(row["club_a"])
                raw_club_b = str(row["club_b"])
                club_a = discord.utils.escape_markdown(raw_club_a)
                club_b = discord.utils.escape_markdown(raw_club_b)
                emoji_a = _club_emoji(guild, raw_club_a)
                emoji_b = _club_emoji(guild, raw_club_b)

                with closing(summary._conn_for_guild(guild.id)) as conn:
                    manager_a_id = _manager_id(conn, raw_club_a)
                    manager_b_id = _manager_id(conn, raw_club_b)

                manager_a = _mention(manager_a_id)
                manager_b = _mention(manager_b_id)
                mention_ids = list(
                    dict.fromkeys(
                        int(user_id)
                        for user_id in (manager_a_id, manager_b_id)
                        if user_id
                    )
                )
                ping_content = (
                    "🔥 " + " vs ".join(_mention(user_id) for user_id in mention_ids)
                    + " — ya tienen clásico oficial."
                    if mention_ids
                    else None
                )

                embed = discord.Embed(
                    title="🔥 ¡SE PICÓ! HAY NUEVO CLÁSICO EN AJPA",
                    description=(
                        f"⚔️ **{emoji_a} {club_a} vs {emoji_b} {club_b}**\n"
                        f"👔 {emoji_a} **{club_a}** — DT: {manager_a}\n"
                        f"👔 {emoji_b} **{club_b}** — DT: {manager_b}\n\n"
                        "Acá se juega por la camiseta y por el derecho a gastar al otro hasta la revancha.\n\n"
                        "🏟️ El que gana, carga. El que pierde, se la banca. ¡Ahora hay que hablar adentro de la cancha!"
                    ),
                    color=discord.Color.gold(),
                )
                embed.set_footer(text="AJPA Transfer Market • Clásico oficial")
                allowed_mentions = _allowed_mentions()
                try:
                    message = await channel.send(
                        content=ping_content,
                        embed=embed,
                        allowed_mentions=allowed_mentions,
                    )
                except (discord.Forbidden, discord.HTTPException):
                    fallback = f"{embed.title}\n\n{embed.description}"
                    if ping_content:
                        fallback = f"{ping_content}\n\n{fallback}"
                    message = await channel.send(
                        content=fallback,
                        allowed_mentions=allowed_mentions,
                    )
                summary._remember_announcement(guild.id, KIND, classic_id, channel.id, message.id)
            with closing(summary._conn_for_guild(guild.id)) as conn:
                conn.execute("DELETE FROM classic_market_outbox WHERE classic_id=?", (classic_id,))
                conn.commit()


def install(bot):
    if getattr(bot, "_ajpa_classic_market_worker", None) is not None:
        return

    @tasks.loop(seconds=15)
    async def worker():
        for guild in bot.guilds:
            try:
                await publish_pending(guild)
            except Exception as exc:
                # Failed delivery must never undo the accepted classic.
                print(f"AJPA classic announcement guild={guild.id}: {type(exc).__name__}: {exc}")

    async def on_ready():
        if not worker.is_running():
            worker.start()

    bot.add_listener(on_ready, "on_ready")
    bot._ajpa_classic_market_worker = worker
