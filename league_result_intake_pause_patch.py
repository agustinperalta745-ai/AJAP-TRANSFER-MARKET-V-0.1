"""Hard pause for AJAP league result intake.

While this module is active, messages in the configured Liga result channel are
ignored by the result pipeline. Images are NOT downloaded, OCR is NOT executed,
OpenAI is NOT called, and no result/scorer/review/evidence records are written.

IMPORTANT: older Liga patches reinstall their handler again inside Bot.run just
before Discord connects. Therefore changing only ``league.handle`` at import time
is not enough. This kill switch also replaces the late feedback/evidence handler
symbols that those startup guards resolve dynamically.
"""

from __future__ import annotations

from pathlib import Path

import discord

import league_automation_patch as league

try:
    import league_result_feedback_patch as feedback
except Exception:
    feedback = None

try:
    import league_result_evidence_patch as evidence
except Exception:
    evidence = None

try:
    import league_runtime_result_rescue_patch as rescue
except Exception:
    rescue = None


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


def _install_hard_pause() -> None:
    """Patch every late-bound result entry point used during AJAP startup."""
    league.handle = _paused_result_handle

    # league_result_feedback_patch has a Bot.run guard that executes AFTER this
    # module is imported and previously reactivated result reading. It assigns
    # ``league.handle = _feedback_handle`` at connection time, so replace that
    # module-global symbol itself. The late guard will now reinstall PAUSE.
    if feedback is not None:
        feedback._feedback_handle = _paused_result_handle

    # Defensive aliases: these functions are also reinstalled by older startup
    # layers in some deployments. Keeping the symbols paused prevents a future
    # installer from bypassing the kill switch.
    if evidence is not None:
        evidence.evidence_handle = _paused_result_handle
    if rescue is not None:
        rescue.reliable_evidence_handle = _paused_result_handle


_install_hard_pause()

print(
    "AJAP Liga: RESULTADOS EN PAUSA TOTAL REAL; "
    "late Bot.run guards bloqueados, sin descarga, OCR, OpenAI ni escrituras"
)
