"""Publish committed classic confirmations to the existing public market feed."""

import asyncio
from contextlib import closing

import discord
from discord.ext import tasks

import market_rumor_patch as rumors
import public_market_summary_patch as summary

KIND = "CLASSIC_CONFIRMED"
_locks = {}


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
                club_a = discord.utils.escape_markdown(str(row["club_a"]))
                club_b = discord.utils.escape_markdown(str(row["club_b"]))
                embed = discord.Embed(
                    title="🔥 ¡SE PICÓ! HAY NUEVO CLÁSICO EN AJPA",
                    description=(
                        f"⚔️ **{club_a} vs {club_b}**\n\n"
                        "Acá se juega por la camiseta y por el derecho a gastar al otro hasta la revancha.\n\n"
                        "🏟️ El que gana, carga. El que pierde, se la banca. ¡Ahora hay que hablar adentro de la cancha!"
                    ),
                    color=discord.Color.gold(),
                )
                embed.set_footer(text="AJPA Transfer Market • Clásico oficial")
                try:
                    message = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                except (discord.Forbidden, discord.HTTPException):
                    message = await channel.send(
                        content=f"{embed.title}\n\n{embed.description}",
                        allowed_mentions=discord.AllowedMentions.none(),
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
