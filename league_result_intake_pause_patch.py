"""AJAP Liga result intake pause state.

Automatic screenshot/result intake is intentionally paused by Staff request.
The rest of the bot remains active. This module keeps the result handlers paused
on startup and reconnects; it does not resume them automatically.
"""
from __future__ import annotations

from pathlib import Path

import discord

import guild_isolation_patch as guild_isolation
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


def _install_pause() -> None:
    league.handle = _paused_result_handle
    if feedback is not None:
        feedback._feedback_handle = _paused_result_handle
    if evidence is not None:
        evidence.evidence_handle = _paused_result_handle
    if rescue is not None:
        rescue.reliable_evidence_handle = _paused_result_handle


async def _keep_paused_on_ready():
    _install_pause()
    print("AJAP Liga: carga automatica de resultados EN PAUSA")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    _install_pause()
    if getattr(runtime, "_ajap_result_pause_active", False):
        return
    if not getattr(bot, "_ajap_result_pause_listener", False):
        bot.add_listener(_keep_paused_on_ready, "on_ready")
        bot._ajap_result_pause_listener = True
    runtime._ajap_result_pause_active = True


_install_pause()

_PREVIOUS = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _PREVIOUS(runtime, bot)
    _install(runtime, bot)
    _install_pause()


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_result_pause_wrapper", False):
    _apply._ajap_result_pause_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply

print("AJAP Liga: carga automatica de resultados DESACTIVADA")
