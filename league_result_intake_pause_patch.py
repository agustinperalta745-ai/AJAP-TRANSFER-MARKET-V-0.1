"""Temporary hard pause for AJAP league result intake.

While this module is imported, the Liga on_message handler will not OCR, stage,
confirm or persist any new result/scorer submission from the configured results
channel. The rest of the bot and all already-persisted league data stay intact.

A capture posted in the configured intake channel only receives a pause reaction
so players can see that automatic loading is intentionally disabled.
"""

from __future__ import annotations

import discord

import league_automation_patch as league


async def _paused_result_handle(runtime, bot, message):
    if not getattr(message, "guild", None) or getattr(getattr(message, "author", None), "bot", False):
        return

    # The listener calls this handler for all messages. Only identify the
    # configured Liga intake channel so the pause marker is not added elsewhere.
    try:
        conn = league.db(runtime, int(message.guild.id), must_exist=True)
    except Exception:
        conn = None
    if conn is None:
        return
    try:
        cfg = conn.execute(
            "SELECT intake_channel_id FROM league_config WHERE guild_id=? LIMIT 1",
            (int(message.guild.id),),
        ).fetchone()
    except Exception:
        cfg = None
    finally:
        conn.close()

    if not cfg or not cfg["intake_channel_id"]:
        return
    if int(getattr(getattr(message, "channel", None), "id", 0) or 0) != int(cfg["intake_channel_id"]):
        return

    # No OCR, no evidence staging, no review card and no DB write. A small
    # reaction on image submissions makes the temporary pause visible to users.
    if getattr(message, "attachments", None):
        try:
            await message.add_reaction("⏸️")
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass
    return


# The original Liga message listener resolves this module global dynamically on
# every message, so replacing it here freezes both image intake and the text
# result wrapper that had been layered on top of it.
league.handle = _paused_result_handle

print("AJAP Liga: CARGA AUTOMÁTICA DE RESULTADOS PAUSADA temporalmente (sin OCR ni escrituras)")
