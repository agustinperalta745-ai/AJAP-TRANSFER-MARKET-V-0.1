"""Visible feedback guard for AJAP Liga result uploads.

The evidence workflow is intentionally strict, but an ignored/misconfigured channel
used to look exactly like a broken bot. This final wrapper guarantees visible
feedback around image uploads without changing the evidence rules:
- warn in channels named like "resultados" when they are not the configured intake;
- add an immediate hourglass while a configured screenshot is being processed;
- leave a lightweight reaction that reflects partial/review/pending state.
"""

from __future__ import annotations

import unicodedata

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league


APP = None
BOT = None
_ORIGINAL_HANDLE = None


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.casefold()


def _looks_like_results_channel(channel) -> bool:
    return "resultado" in _norm(getattr(channel, "name", ""))


def _config(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            "SELECT * FROM league_config WHERE guild_id = ? LIMIT 1",
            (int(guild_id),),
        ).fetchone()
    finally:
        conn.close()


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _source_state(runtime, guild_id: int, message_id: int):
    """Return enough persisted state to choose a visible reaction after processing."""
    conn = league.db(runtime, int(guild_id))
    try:
        match = conn.execute(
            "SELECT 1 FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(message_id),),
        ).fetchone()

        evidence = None
        if _table_exists(conn, "league_result_evidence"):
            evidence = conn.execute(
                "SELECT status FROM league_result_evidence WHERE source_message_id=? LIMIT 1",
                (int(message_id),),
            ).fetchone()

        review = None
        if _table_exists(conn, "league_manual_reviews"):
            review = conn.execute(
                "SELECT status FROM league_manual_reviews WHERE source_message_id=? LIMIT 1",
                (int(message_id),),
            ).fetchone()

        return {
            "match": bool(match),
            "evidence": str(evidence["status"] or "").upper() if evidence else "",
            "review": str(review["status"] or "").upper() if review else "",
        }
    finally:
        conn.close()


async def _safe_react(message, emoji: str):
    try:
        await message.add_reaction(emoji)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def _remove_processing(message):
    try:
        await league.remove_hourglass(message)
    except Exception:
        try:
            me = message.guild.me if message.guild else None
            if me:
                await message.remove_reaction("⏳", me)
        except Exception:
            pass


async def _feedback_handle(runtime, bot, message):
    if not message.guild or message.author.bot or not message.attachments:
        return await _ORIGINAL_HANDLE(runtime, bot, message)

    cfg = _config(runtime, message.guild.id)
    intake_id = int(cfg["intake_channel_id"]) if cfg and cfg["intake_channel_id"] else None

    # A channel clearly intended for results should never fail silently. We do
    # not auto-bind it because only Staff should decide the official intake.
    if intake_id is None:
        if _looks_like_results_channel(message.channel):
            await _safe_react(message, "⚠️")
            await message.reply(
                "⚠️ **Este canal todavía no está vinculado al lector de resultados.**\n"
                "Staff: abrí **Administración → Gestión → Configurar resultados** y elegí este canal. "
                "Después reenviá la captura.",
                mention_author=False,
            )
        return

    if int(message.channel.id) != intake_id:
        if _looks_like_results_channel(message.channel):
            await _safe_react(message, "⚠️")
            await message.reply(
                f"⚠️ Esta captura no se procesó porque el canal automático configurado es <#{intake_id}>. "
                "Si este canal debe reemplazarlo, cambialo desde **Administración → Gestión → Configurar resultados**.",
                mention_author=False,
            )
        return

    # Immediate acknowledgement: image analysis can take several seconds.
    await _safe_react(message, "⏳")
    try:
        await _ORIGINAL_HANDLE(runtime, bot, message)
    finally:
        await _remove_processing(message)

    try:
        state = _source_state(runtime, message.guild.id, message.id)
    except Exception as exc:
        print(f"AJAP Liga feedback: no se pudo leer estado mensaje={message.id}: {exc}")
        return

    if state["match"]:
        # The evidence layer already adds ✅ after persistence.
        return

    if state["review"]:
        await _safe_react(message, "⚠️")
        return

    if state["evidence"] == "PARCIAL":
        await _safe_react(message, "🟡")
        return

    if state["evidence"] == "REANUDACION_PENDIENTE":
        await _safe_react(message, "🔄")
        return

    if state["evidence"] == "ESPERANDO_TIPO":
        await _safe_react(message, "❓")
        return


def apply_league_result_feedback_patch(runtime, bot):
    global APP, BOT, _ORIGINAL_HANDLE
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_league_result_feedback_patch", False):
        return

    # At this point the evidence patch has already replaced league.handle.
    _ORIGINAL_HANDLE = league.handle
    league.handle = _feedback_handle
    runtime._ajap_league_result_feedback_patch = True
    print("AJAP Liga feedback visible activo: canal + procesamiento + estados")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_result_feedback(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_league_result_feedback_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_league_result_feedback_wrapped",
    False,
):
    _apply_guild_isolation_then_result_feedback._ajap_league_result_feedback_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_result_feedback
