"""Automatically retry still-pending Liga screenshots after reader upgrades.

This prevents admins from having to manually reconstruct results/goleadores that
were already posted while an older OCR version was too strict.  On the first
ready event of each process, AJAP revisits only unresolved manual-review rows
that do not already have an official league_match, clears the stale review/hash
state for that source message, and sends the ORIGINAL Discord message through
the currently installed result pipeline.

Already official matches are never touched.  If the new reader still cannot
prove a result, the normal Staff review is recreated.
"""

from __future__ import annotations

import asyncio

import league_automation_patch as league
import league_result_evidence_patch as evidence
import league_validation_admin_review_patch as strict


_DONE_GUILDS = set()


def _pending_rows(runtime, guild_id: int):
    evidence._ensure_schema(runtime, guild_id)
    strict._ensure_schema(runtime, guild_id)
    conn = league.db(runtime, guild_id)
    try:
        return conn.execute(
            """
            SELECT r.source_message_id, r.source_channel_id,
                   r.staff_channel_id, r.staff_message_id
            FROM league_manual_reviews r
            LEFT JOIN league_matches m
              ON m.source_message_id = r.source_message_id
            WHERE UPPER(COALESCE(r.status, 'PENDIENTE'))='PENDIENTE'
              AND m.source_message_id IS NULL
            ORDER BY r.created_at ASC
            LIMIT 200
            """
        ).fetchall()
    finally:
        conn.close()


def _reset_pending_source(runtime, guild_id: int, source_message_id: int):
    conn = league.db(runtime, guild_id)
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Never remove an already official match/scorers here.
        official = conn.execute(
            "SELECT 1 FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
        if official:
            conn.rollback()
            return False
        conn.execute(
            "DELETE FROM league_result_evidence WHERE source_message_id=?",
            (int(source_message_id),),
        )
        conn.execute(
            "DELETE FROM league_manual_reviews WHERE source_message_id=?",
            (int(source_message_id),),
        )
        conn.execute(
            "DELETE FROM league_image_hashes WHERE source_message_id=?",
            (int(source_message_id),),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _fetch_text_channel(bot, guild, channel_id: int):
    channel = guild.get_channel(int(channel_id)) if guild else None
    if channel is not None:
        return channel
    try:
        return await bot.fetch_channel(int(channel_id))
    except Exception:
        return None


async def _disable_old_staff_card(bot, guild, row):
    staff_channel_id = row["staff_channel_id"]
    staff_message_id = row["staff_message_id"]
    if not staff_channel_id or not staff_message_id:
        return
    channel = await _fetch_text_channel(bot, guild, int(staff_channel_id))
    if channel is None or not hasattr(channel, "fetch_message"):
        return
    try:
        message = await channel.fetch_message(int(staff_message_id))
        await message.edit(view=None)
    except Exception:
        pass


async def _retry_guild(runtime, bot, guild):
    guild_id = int(guild.id)
    if guild_id in _DONE_GUILDS:
        return
    _DONE_GUILDS.add(guild_id)

    try:
        rows = _pending_rows(runtime, guild_id)
    except Exception as exc:
        print(f"WARNING AJAP pending review scan guild={guild_id}: {exc}")
        return
    if not rows:
        return

    recovered = 0
    retried = 0
    for row in rows:
        source_channel = await _fetch_text_channel(bot, guild, int(row["source_channel_id"]))
        if source_channel is None or not hasattr(source_channel, "fetch_message"):
            continue
        try:
            source = await source_channel.fetch_message(int(row["source_message_id"]))
        except Exception:
            continue
        if not getattr(source, "attachments", None):
            continue

        try:
            await _disable_old_staff_card(bot, guild, row)
            if not _reset_pending_source(runtime, guild_id, int(row["source_message_id"])):
                continue
            retried += 1
            await league.handle(runtime, bot, source)

            conn = league.db(runtime, guild_id)
            try:
                now_official = conn.execute(
                    "SELECT 1 FROM league_matches WHERE source_message_id=? LIMIT 1",
                    (int(row["source_message_id"]),),
                ).fetchone()
            finally:
                conn.close()
            if now_official:
                recovered += 1
        except Exception as exc:
            print(
                f"WARNING AJAP pending review retry source={row['source_message_id']}: "
                f"{type(exc).__name__}: {exc}"
            )
        # Avoid a burst of Discord/API work when many old captures exist.
        await asyncio.sleep(0.35)

    print(
        f"AJAP Liga pending review retry guild={guild_id}: "
        f"reintentados={retried} recuperados={recovered}"
    )


def install_pending_review_reprocess(runtime, bot):
    if getattr(bot, "_ajap_pending_review_reprocess_listener", False):
        return

    async def _on_ready():
        for guild in list(bot.guilds):
            await _retry_guild(runtime, bot, guild)

    bot.add_listener(_on_ready, "on_ready")
    bot._ajap_pending_review_reprocess_listener = True
    print("AJAP Liga: reproceso automático de revisiones pendientes ACTIVO")


# Imported before run_bot creates the final runtime.  Hook Bot.run so the
# listener is installed after all AJAP patches/views/handlers are ready.
try:
    import sys
    from discord.ext import commands

    _ORIGINAL_RUN = commands.Bot.run

    def _run_with_pending_review_reprocess(self, token, *args, **kwargs):
        runtime = sys.modules.get("ajap_bot_runtime")
        if runtime is not None:
            try:
                install_pending_review_reprocess(runtime, self)
            except Exception as exc:
                print(f"WARNING AJAP pending review listener install: {exc}")
        return _ORIGINAL_RUN(self, token, *args, **kwargs)

    if not getattr(commands.Bot.run, "_ajap_pending_review_reprocess", False):
        _run_with_pending_review_reprocess._ajap_pending_review_reprocess = True
        commands.Bot.run = _run_with_pending_review_reprocess
except Exception as exc:
    print(f"WARNING AJAP pending review patch import: {exc}")
