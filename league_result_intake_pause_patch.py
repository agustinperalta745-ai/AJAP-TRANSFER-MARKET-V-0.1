"""AJAP Liga result intake resume state.

The emergency hard pause was explicitly lifted by Staff. This module now keeps
the exact active screenshot/text result pipeline that existed immediately before
the old pause layer, so new captures are processed again on startup.

The historical checkpoint remains available for diagnostics, but it no longer
blocks live intake or replaces the active reader with the paused handler.
"""
from __future__ import annotations

from pathlib import Path

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league

# Load the stricter PES6 score parser before freezing the current active handlers.
import league_scoreboard_reader_v2_patch  # noqa: F401

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

# Capture the real active pipeline. This is now the pipeline we KEEP active.
_ACTIVE_LEAGUE_HANDLE = league.handle
_ACTIVE_FEEDBACK_HANDLE = getattr(feedback, "_feedback_handle", None) if feedback is not None else None
_ACTIVE_EVIDENCE_HANDLE = getattr(evidence, "evidence_handle", None) if evidence is not None else None
_ACTIVE_RESCUE_HANDLE = getattr(rescue, "reliable_evidence_handle", None) if rescue is not None else None

# Keep the old checkpoint module loaded so its schema/marker remains compatible
# with the data already written during the pause period. It is no longer a gate.
import league_post_pause_checkpoint_60_patch as checkpoint  # noqa: E402

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
APP = None
BOT = None


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
    """Legacy paused handler kept only for compatibility; it is not installed."""
    if not getattr(message, "guild", None):
        return
    if getattr(getattr(message, "author", None), "bot", False):
        return

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

    attachments = list(getattr(message, "attachments", None) or [])
    if any(_is_image_attachment(item) for item in attachments):
        await _safe_reaction(message, "⏸️")


def _install_startup_gate() -> None:
    """Legacy function retained for compatibility. Do not call while intake is live."""
    league.handle = _paused_result_handle
    if feedback is not None:
        feedback._feedback_handle = _paused_result_handle
    if evidence is not None:
        evidence.evidence_handle = _paused_result_handle
    if rescue is not None:
        rescue.reliable_evidence_handle = _paused_result_handle


def _restore_active_pipeline() -> None:
    league.handle = _ACTIVE_LEAGUE_HANDLE
    if feedback is not None and _ACTIVE_FEEDBACK_HANDLE is not None:
        feedback._feedback_handle = _ACTIVE_FEEDBACK_HANDLE
    if evidence is not None and _ACTIVE_EVIDENCE_HANDLE is not None:
        evidence.evidence_handle = _ACTIVE_EVIDENCE_HANDLE
    if rescue is not None and _ACTIVE_RESCUE_HANDLE is not None:
        rescue.reliable_evidence_handle = _ACTIVE_RESCUE_HANDLE


def _checkpoint_ready(runtime, guild_id: int) -> tuple[bool, int | None]:
    conn = league.db(runtime, int(guild_id), must_exist=True)
    if conn is None:
        return False, None
    try:
        row = conn.execute(
            "SELECT match_count_after FROM league_post_pause_checkpoint_state "
            "WHERE marker=? LIMIT 1",
            (checkpoint.MARKER,),
        ).fetchone()
        if not row:
            return False, None
        count = int(row["match_count_after"])
        return count >= 60, count
    except Exception:
        return False, None
    finally:
        conn.close()


async def _resume_after_checkpoint():
    """Reassert live intake on every ready event; checkpoint is informational only."""
    if APP is None or BOT is None:
        return
    _restore_active_pipeline()
    guild = BOT.get_guild(int(guild_isolation.LEGACY_GUILD_ID))
    if guild is None:
        print("AJAP Liga: RESULTADOS REACTIVADOS; lector de capturas activo")
        return
    ready, count = _checkpoint_ready(APP, guild.id)
    print(
        "AJAP Liga: RESULTADOS REACTIVADOS; lector de capturas activo | "
        f"checkpoint_ready={ready} matches={count!r}"
    )


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_result_resume_gate", False):
        return
    if not getattr(bot, "_ajap_result_resume_gate_listener", False):
        bot.add_listener(_resume_after_checkpoint, "on_ready")
        bot._ajap_result_resume_gate_listener = True
    runtime._ajap_result_resume_gate = True


# IMPORTANT: do NOT install the emergency pause. Keep the current reader live.
_restore_active_pipeline()

_PREVIOUS = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _PREVIOUS(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_result_resume_gate_wrapper", False):
    _apply._ajap_result_resume_gate_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply

print("AJAP Liga: captura de resultados REHABILITADA; emergencia de pausa desactivada")
