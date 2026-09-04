"""Temporary result-intake freeze with an admin-only PaddleOCR shadow test.

Production result persistence remains HARD PAUSED: this handler never stages,
confirms or writes a result/scorer record. Normal players still only receive a
pause reaction in the configured result channel.

An administrator/manage-guild user may post one image in that same channel to
exercise the new local PaddleOCR reader. The bot replies with what it *would*
read, but deliberately does not call any persistence/review/evidence path.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import discord

import league_automation_patch as league


_PADDLE_TEST_LOCK = asyncio.Lock()
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_REPO_ROOT = Path(__file__).resolve().parent
_PADDLE_PROBE = _REPO_ROOT / "tools" / "pes6_paddle_probe_ready.py"


def _is_image_attachment(attachment) -> bool:
    content_type = str(getattr(attachment, "content_type", "") or "").lower()
    if content_type.startswith("image/"):
        return True
    suffix = Path(str(getattr(attachment, "filename", "") or "")).suffix.lower()
    return suffix in _IMAGE_SUFFIXES


def _can_shadow_test(member) -> bool:
    perms = getattr(member, "guild_permissions", None)
    return bool(
        getattr(perms, "administrator", False)
        or getattr(perms, "manage_guild", False)
    )


async def _safe_reaction(message, emoji: str) -> None:
    try:
        await message.add_reaction(emoji)
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        pass


async def _safe_status(message, text: str):
    try:
        return await message.reply(
            text,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        return None


async def _edit_status(status, text: str) -> None:
    if status is None:
        return
    try:
        await status.edit(content=text, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        pass


async def _run_paddle_probe(image_bytes: bytes, filename: str) -> dict:
    suffix = Path(str(filename or "capture.jpg")).suffix.lower()
    if suffix not in _IMAGE_SUFFIXES:
        suffix = ".jpg"

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="ajap-paddle-shadow-", suffix=suffix, delete=False) as tmp:
            tmp.write(image_bytes)
            temp_path = Path(tmp.name)

        env = os.environ.copy()
        env.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
        env.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(_PADDLE_PROBE),
            str(temp_path),
            cwd=str(_REPO_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return {"shadow_error": "timeout_180s"}

        raw_out = stdout.decode("utf-8", errors="replace").strip()
        raw_err = stderr.decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(raw_out) if raw_out else {}
        except Exception:
            payload = {}

        if not isinstance(payload, dict):
            payload = {}
        payload["shadow_exit_code"] = int(proc.returncode or 0)
        if raw_err:
            payload["shadow_stderr_tail"] = raw_err[-1200:]
        if not payload.get("source") and not payload.get("screen_kind"):
            payload["shadow_error"] = "probe_no_json"
        return payload
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def _result_text(payload: dict) -> str:
    if payload.get("result_complete") is True and payload.get("screen_kind") == "result":
        home = str(payload.get("home_team") or "?")
        away = str(payload.get("away_team") or "?")
        hg = payload.get("home_goals")
        ag = payload.get("away_goals")
        elapsed = payload.get("elapsed_seconds")
        source = str(payload.get("score_source") or "PaddleOCR")
        elapsed_line = f"\n⏱️ OCR: **{elapsed}s**" if elapsed is not None else ""
        return (
            "🧪 **PRUEBA DEL LECTOR NUEVO**\n"
            f"✅ **{discord.utils.escape_markdown(home)} {hg}–{ag} {discord.utils.escape_markdown(away)}**\n"
            f"🔎 Marcador validado por: `{discord.utils.escape_markdown(source)}`"
            f"{elapsed_line}\n"
            "🔒 **No se cargó ni modificó ningún resultado de la Liga.**"
        )

    if payload.get("screen_kind") == "scorers":
        return (
            "🧪 **PRUEBA DEL LECTOR NUEVO**\n"
            "ℹ️ Detecté una pantalla de goleadores, no un resultado final.\n"
            "🔒 **No se cargó ni modificó ningún dato de la Liga.**"
        )

    err = str(payload.get("shadow_error") or "")
    if err:
        return (
            "🧪 **PRUEBA DEL LECTOR NUEVO**\n"
            f"⚠️ El lector no pudo completar esta prueba (`{discord.utils.escape_markdown(err)}`).\n"
            "🔒 **No se cargó ni modificó ningún dato de la Liga.**"
        )

    return (
        "🧪 **PRUEBA DEL LECTOR NUEVO**\n"
        "❌ Esta captura **no sería aceptada automáticamente** como resultado oficial.\n"
        "Eso es intencional: si no puede demostrar equipos + marcador + pantalla final, rechaza.\n"
        "🔒 **No se cargó ni modificó ningún dato de la Liga.**"
    )


async def _paused_result_handle(runtime, bot, message):
    if not getattr(message, "guild", None) or getattr(getattr(message, "author", None), "bot", False):
        return

    # The listener calls this handler for all messages. Only identify the
    # configured Liga intake channel; no result tables are touched.
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
    image = next((item for item in attachments if _is_image_attachment(item)), None)
    if image is None:
        return

    # Normal league users remain fully paused. Only Staff/admin can exercise
    # the no-write shadow reader while it is being validated in Discord.
    if not _can_shadow_test(getattr(message, "author", None)):
        await _safe_reaction(message, "⏸️")
        return

    await _safe_reaction(message, "🧪")
    status = await _safe_status(
        message,
        "🧪 **Probando el lector nuevo…**\n"
        "🔒 Modo prueba: esta captura **no se va a cargar** en la Liga.\n"
        "La primera lectura después de un despliegue puede tardar mientras se preparan los modelos.",
    )

    if not _PADDLE_PROBE.exists():
        await _edit_status(
            status,
            "🧪 **PRUEBA DEL LECTOR NUEVO**\n"
            "⚠️ El ejecutable de prueba no está disponible en este despliegue.\n"
            "🔒 No se cargó ningún resultado.",
        )
        return

    async with _PADDLE_TEST_LOCK:
        try:
            image_bytes = await image.read()
            payload = await _run_paddle_probe(image_bytes, getattr(image, "filename", "capture.jpg"))
        except Exception as exc:
            print(f"AJAP Paddle shadow error: {type(exc).__name__}: {exc}")
            payload = {"shadow_error": type(exc).__name__}

    print(
        "AJAP Paddle shadow: "
        f"guild={message.guild.id} author={getattr(message.author, 'id', None)} "
        f"kind={payload.get('screen_kind')} complete={payload.get('result_complete')} "
        f"home={payload.get('home_team')} hg={payload.get('home_goals')} "
        f"ag={payload.get('away_goals')} away={payload.get('away_team')} "
        "persisted=False"
    )
    await _edit_status(status, _result_text(payload))
    return


# The original Liga message listener resolves this module global dynamically on
# every message. Replacing it here keeps every image/text persistence wrapper
# bypassed while exposing only the explicit admin shadow test above.
league.handle = _paused_result_handle

print(
    "AJAP Liga: CARGA AUTOMÁTICA DE RESULTADOS PAUSADA; "
    "PaddleOCR shadow test habilitado solo para Staff (sin escrituras)"
)
