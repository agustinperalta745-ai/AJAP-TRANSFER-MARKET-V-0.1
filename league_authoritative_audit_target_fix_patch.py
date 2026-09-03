"""Find the real AJPA GES channel at runtime and apply the audited 03/09 rebuild there.

Do not trust a hard-coded guild id for this one-time repair. The production bot has
moved between guild-isolated databases during rollout, while the visible Discord
channel is authoritative for where Staff is actually working.

This bridge:
- discovers the configured GES channel in every connected guild;
- also recovers the exact #resultados-para-cargar channel if its DB config was lost;
- only selects a recovered channel when it already contains AJPA bot GES cards;
- runs the 38-match audited reconciliation in that guild DB;
- requires the channel to be truly empty before republishing;
- uses a new v3 marker so failed/wrong-guild v1/v2 attempts cannot suppress it.
"""
from __future__ import annotations

import os

import discord

import competition_cycle as cycle
import guild_isolation_patch as guild_isolation
import league_authoritative_audit_reconcile_patch as reconcile
import league_ges_result_queue_patch as ges


CHANNEL_NAME = "resultados-para-cargar"
reconcile.MARKER = "authoritative_preseason_audit_2026_09_03_v3_discovered_ges"


async def _strict_purge_channel(channel):
    """Delete everything and prove the channel is empty before rebuilding it."""
    before = [message async for message in channel.history(limit=None, oldest_first=False)]
    if not before:
        return 0

    deleted_count = 0
    try:
        deleted = await channel.purge(
            limit=None,
            check=lambda _message: True,
            bulk=True,
            reason="AJPA: reconstrucción oficial GES 03/09/2026",
        )
        deleted_count = len(deleted)
    except Exception as bulk_exc:
        print(
            "AJAP GES strict cleanup: bulk purge failed; trying individual deletes: "
            f"{type(bulk_exc).__name__}: {bulk_exc}"
        )
        for message in before:
            try:
                await message.delete()
                deleted_count += 1
            except Exception as exc:
                raise RuntimeError(
                    "GES no pudo limpiarse por completo. "
                    f"message={getattr(message, 'id', '?')} "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

    remaining = [message async for message in channel.history(limit=5, oldest_first=False)]
    if remaining:
        raise RuntimeError(
            "GES cleanup verification failed: todavía quedan mensajes en el canal "
            f"después de intentar borrar {deleted_count}."
        )
    return deleted_count


reconcile._purge_channel = _strict_purge_channel


def _configured_channel(runtime, guild):
    try:
        channel_id = ges._get_channel_id(runtime, guild.id)
    except Exception:
        channel_id = None
    if not channel_id:
        return None
    channel = guild.get_channel(int(channel_id))
    return channel if isinstance(channel, discord.TextChannel) else None


async def _looks_like_existing_ges(bot, channel):
    """Recover only a channel that visibly contains this bot's old GES cards."""
    try:
        async for message in channel.history(limit=40, oldest_first=False):
            if not bot.user or int(message.author.id) != int(bot.user.id):
                continue
            for embed in message.embeds:
                title = str(embed.title or "").casefold()
                footer = str(getattr(embed.footer, "text", "") or "").casefold()
                if "resultado cerrado" in title or "ges liga" in title or "ges liga" in footer:
                    return True
    except Exception as exc:
        print(
            f"AJAP GES discovery history failed guild={channel.guild.id} channel={channel.id}: "
            f"{type(exc).__name__}: {exc}"
        )
    return False


async def _discover_channel(runtime, bot, guild):
    configured = _configured_channel(runtime, guild)
    if configured is not None:
        return configured

    # The screenshot-confirmed production channel has this exact name. We only
    # recover it when it already contains AJPA bot GES cards, so another server
    # cannot be rewritten merely for reusing the same channel name.
    for channel in guild.text_channels:
        if str(channel.name).casefold() != CHANNEL_NAME:
            continue
        if await _looks_like_existing_ges(bot, channel):
            try:
                ges._save_channel(runtime, guild.id, channel.id, 0)
                print(
                    f"AJAP GES discovery: recovered config guild={guild.id} "
                    f"channel={channel.id} #{channel.name}"
                )
            except Exception as exc:
                print(
                    f"AJAP GES discovery config save failed guild={guild.id}: "
                    f"{type(exc).__name__}: {exc}"
                )
                return None
            return channel
    return None


def _force_preseason_state(runtime, guild_id):
    """Repair only the rollout state required by the already-declared Pretemporada."""
    conn = reconcile.league.db(runtime, int(guild_id))
    try:
        cycle.ensure_schema(conn)
        row = conn.execute(
            "SELECT phase,season_number,competition_id FROM competition_cycle_state WHERE id=1"
        ).fetchone()
        if row and str(row["phase"] or "") == cycle.PRESEASON and row["competition_id"] is not None:
            conn.commit()
            return int(row["competition_id"])

        # This audit is explicitly the exceptional initial Pretemporada. If the
        # rollout DB was left as Temporada 1, relabel the active edition instead
        # of creating/resetting any historical data.
        if row and str(row["phase"] or "") == cycle.SEASON and int(row["season_number"] or 1) == 1:
            cid = int(row["competition_id"]) if row["competition_id"] is not None else None
            if cid is None:
                cur = conn.execute(
                    "INSERT INTO competition_editions(kind,season_number,label,status) "
                    "VALUES('preseason',1,'Pretemporada','active')"
                )
                cid = int(cur.lastrowid)
            else:
                conn.execute(
                    "UPDATE competition_editions SET kind='preseason',label='Pretemporada',status='active' WHERE id=?",
                    (cid,),
                )
            conn.execute(
                "UPDATE competition_cycle_state SET phase='preseason',competition_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
                (cid,),
            )
            if "competition_id" in reconcile._cols(conn, "league_matches"):
                conn.execute(
                    "UPDATE league_matches SET competition_id=? WHERE competition_id IS NULL OR competition_id=?",
                    (cid, int(row["competition_id"]) if row["competition_id"] is not None else cid),
                )
            if "competition_id" in reconcile._cols(conn, "league_goal_events"):
                conn.execute(
                    "UPDATE league_goal_events SET competition_id=? WHERE competition_id IS NULL OR competition_id=?",
                    (cid, int(row["competition_id"]) if row["competition_id"] is not None else cid),
                )
            conn.commit()
            print(f"AJAP audit cycle repair: guild={guild_id} Temporada 1 -> Pretemporada cid={cid}")
            return cid

        conn.commit()
        return None
    finally:
        conn.close()


async def _run_discovered_authoritative_reconcile():
    runtime, bot = reconcile.APP, reconcile.BOT
    if runtime is None or bot is None or not bot.user:
        return

    processed = 0
    for guild in list(bot.guilds):
        channel = await _discover_channel(runtime, bot, guild)
        if channel is None:
            continue
        processed += 1
        try:
            reconcile.TARGET_GUILD_ID = int(guild.id)
            _force_preseason_state(runtime, guild.id)
            changed, _cid = reconcile._rebuild_database(runtime, guild.id)
            if changed:
                try:
                    await reconcile.league.refresh(runtime, bot, guild.id)
                except Exception as exc:
                    print(
                        f"WARNING AJAP authoritative table refresh guild={guild.id}: "
                        f"{type(exc).__name__}: {exc}"
                    )
            rebuilt = await reconcile._rebuild_ges(runtime, bot, guild)
            print(
                f"AJAP discovered authoritative reconcile finished guild={guild.id} "
                f"channel=#{channel.name} db_changed={changed} ges_rebuilt={rebuilt}"
            )
        except Exception as exc:
            print(
                f"ERROR AJAP discovered authoritative reconcile guild={guild.id} "
                f"channel=#{channel.name}: {type(exc).__name__}: {exc}"
            )

    if processed == 0:
        print("AJAP GES discovery: no configured/recognizable #resultados-para-cargar channel found")


# _install resolves this global only later, when run_bot applies the guild wrapper.
# Replacing it now guarantees the registered on_ready listener is the discovery
# version instead of the obsolete hard-coded-guild version.
reconcile._run_authoritative_reconcile = _run_discovered_authoritative_reconcile

print(
    "AJPA authoritative audit FIX v3: runtime GES discovery + strict wipe + "
    "Pretemporada rollout repair"
)
