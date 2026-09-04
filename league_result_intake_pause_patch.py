"""Hard pause for AJAP league result intake.

While this module is active, messages in the configured Liga result channel are
ignored by the result pipeline. Images are NOT downloaded, OCR is NOT executed,
OpenAI is NOT called, and no result/scorer/review/evidence records are written.

This is intentionally a runtime kill switch. Import it LAST, after every other
league reader patch, so ``league.handle`` points only to the paused handler.
"""

from __future__ import annotations

from pathlib import Path

import discord

import league_automation_patch as league


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _is_image_attachment(attachment) -> bool:
    content_type = str(getattr(attachment, "content_type", "") or "").lower()
    if content_type.startswith("image/"):
        return True
    suffix = Path(str(getattr(attachment, "filename", "") or "")).suffix.lower()
    return suffix in _IMAGE_SUFFIXES


async def _safe_reaction(message, emoji: str) -> None:
    try:
        await message.add_reaction(emoji)
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        pass


async def _paused_result_handle(runtime, bot, message):
    """Ignore all Liga result-channel intake without inspecting its contents."""
    if not getattr(message, "guild", None):
        return
    if getattr(getattr(message, "author", None), "bot", False):
        return

    # Read only the Liga channel configuration. No attachment bytes, OCR,
    # result parsing, review staging or persistence path is touched.
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

    channel_id = int(getattr(getattr(message, "channel", None), "id", 0) or 0)
    if channel_id != int(cfg["intake_channel_id"]):
        return

    # Visible acknowledgement for screenshots only. We deliberately do NOT call
    # attachment.read(), so the bot never downloads or analyzes the result image.
    attachments = list(getattr(message, "attachments", None) or [])
    if any(_is_image_attachment(item) for item in attachments):
        await _safe_reaction(message, "⏸️")

    return


# The Liga listener resolves this module global dynamically for every message.
# Replacing it here is the hard stop for both screenshot and text-result intake.
league.handle = _paused_result_handle

print(
    "AJAP Liga: RESULTADOS EN PAUSA TOTAL; "
    "sin descarga de capturas, OCR, OpenAI, revisión ni escrituras"
)
