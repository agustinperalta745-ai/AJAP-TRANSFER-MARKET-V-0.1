"""Staff helper to replay an old Liga screenshot through the CURRENT live reader."""

from __future__ import annotations

import hashlib
import mimetypes
import re

import discord
from discord import app_commands

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_result_evidence_patch as evidence
import league_validation_admin_review_patch as strict

APP = None
BOT = None

_MESSAGE_LINK_RE = re.compile(
    r"https?://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)(?:/)?(?:\?.*)?$",
    re.IGNORECASE,
)


def _parse_message_link(value: str):
    match = _MESSAGE_LINK_RE.match(str(value or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


async def _fetch_message(interaction: discord.Interaction, link: str):
    parsed = _parse_message_link(link)
    if not parsed:
        raise ValueError("Pegá el enlace completo del mensaje de Discord que contiene la captura.")
    guild_id, channel_id, message_id = parsed
    if not interaction.guild_id or int(interaction.guild_id) != int(guild_id):
        raise ValueError("El mensaje tiene que pertenecer a este mismo servidor.")
    channel = interaction.guild.get_channel(channel_id) if interaction.guild else None
    if channel is None:
        try:
            channel = await BOT.fetch_channel(channel_id)
        except Exception as exc:
            raise ValueError("No pude acceder al canal de ese mensaje.") from exc
    if not hasattr(channel, "fetch_message"):
        raise ValueError("Ese enlace no apunta a un canal de texto compatible.")
    try:
        return await channel.fetch_message(message_id)
    except Exception as exc:
        raise ValueError("No pude encontrar o leer ese mensaje.") from exc


async def _attachment_hashes(message: discord.Message):
    hashes = []
    for att in message.attachments[: league.MAX_IMAGES]:
        mime = (att.content_type or mimetypes.guess_type(att.filename)[0] or "").split(";")[0]
        if not mime.startswith("image/"):
            continue
        if att.size and att.size > league.MAX_BYTES:
            continue
        data = await att.read()
        hashes.append(hashlib.sha256(data).hexdigest())
    return hashes


def _clear_source(runtime, guild_id: int, source_message_id: int, hashes):
    """Clear retry/review state. Final safety may wrap this to preserve official rows."""
    evidence._ensure_schema(runtime, guild_id)
    strict._ensure_schema(runtime, guild_id)
    conn = league.db(runtime, guild_id)
    removed_match = False
    removed_scorers = 0
    old_prompt_id = None
    old_staff_message_id = None
    try:
        evidence_row = conn.execute(
            "SELECT prompt_message_id FROM league_result_evidence WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
        if evidence_row:
            old_prompt_id = evidence_row["prompt_message_id"]
        review_row = conn.execute(
            "SELECT staff_message_id FROM league_manual_reviews WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
        if review_row:
            old_staff_message_id = review_row["staff_message_id"]
        removed_match = bool(conn.execute(
            "SELECT 1 FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone())
        scorers_row = conn.execute(
            "SELECT COUNT(*) AS n FROM league_goal_events WHERE source_message_id=?",
            (int(source_message_id),),
        ).fetchone()
        removed_scorers = int(scorers_row["n"] if scorers_row else 0)

        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM league_goal_events WHERE source_message_id=?", (int(source_message_id),))
        conn.execute("DELETE FROM league_matches WHERE source_message_id=?", (int(source_message_id),))
        conn.execute("DELETE FROM league_result_evidence WHERE source_message_id=?", (int(source_message_id),))
        conn.execute("DELETE FROM league_manual_reviews WHERE source_message_id=?", (int(source_message_id),))
        conn.execute("DELETE FROM league_image_hashes WHERE source_message_id=?", (int(source_message_id),))
        for digest in hashes or []:
            conn.execute("DELETE FROM league_image_hashes WHERE image_hash=?", (str(digest),))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "removed_match": removed_match,
        "removed_scorers": removed_scorers,
        "old_prompt_id": int(old_prompt_id) if old_prompt_id else None,
        "old_staff_message_id": int(old_staff_message_id) if old_staff_message_id else None,
    }


def _source_state(runtime, guild_id: int, source_message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        match = conn.execute(
            "SELECT home_team,away_team,home_goals,away_goals FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
        evidence_status = ""
        review_status = ""
        try:
            row = conn.execute(
                "SELECT status FROM league_result_evidence WHERE source_message_id=? LIMIT 1",
                (int(source_message_id),),
            ).fetchone()
            evidence_status = str(row["status"] or "") if row else ""
        except Exception:
            pass
        try:
            row = conn.execute(
                "SELECT status FROM league_manual_reviews WHERE source_message_id=? LIMIT 1",
                (int(source_message_id),),
            ).fetchone()
            review_status = str(row["status"] or "") if row else ""
        except Exception:
            pass
        return match, evidence_status, review_status
    finally:
        conn.close()


async def _disable_old_workflow_messages(message: discord.Message, state):
    for message_id in (state.get("old_prompt_id"), state.get("old_staff_message_id")):
        if not message_id:
            continue
        try:
            old = await message.channel.fetch_message(int(message_id))
            await old.edit(view=None)
        except Exception:
            pass


async def _clear_old_bot_reactions(message: discord.Message):
    if not BOT or not BOT.user:
        return
    for emoji in ("⏸️", "✅", "❌", "⚠️", "♻️", "⏳", "🟡", "🔄", "❓"):
        try:
            await message.remove_reaction(emoji, BOT.user)
        except Exception:
            pass


@app_commands.command(
    name="rehabilitar_captura_prueba",
    description="Reprocesa una captura con el lector actual (solo Staff).",
)
@app_commands.describe(mensaje="Enlace del mensaje original que contiene la captura")
async def rehabilitar_captura_prueba(interaction: discord.Interaction, mensaje: str):
    runtime = APP
    if runtime is None or BOT is None:
        await interaction.response.send_message("⚠️ El módulo de Liga todavía no está listo.", ephemeral=True)
        return
    if not interaction.guild_id:
        await interaction.response.send_message("⚠️ Usá este comando dentro del servidor.", ephemeral=True)
        return
    if not runtime.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores pueden usar este comando.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        source = await _fetch_message(interaction, mensaje)
        hashes = await _attachment_hashes(source)
        if not hashes:
            await interaction.followup.send("⚠️ Ese mensaje no contiene una imagen válida para Resultados.", ephemeral=True)
            return

        state = _clear_source(runtime, interaction.guild_id, source.id, hashes)
        await _clear_old_bot_reactions(source)
        await _disable_old_workflow_messages(source, state)

        # SAME handler as a brand-new result. It must post the public result,
        # persist scorers, update tables/app and route uncertainty to Staff.
        await league.handle(runtime, BOT, source)

        match, evidence_status, review_status = _source_state(
            runtime, interaction.guild_id, source.id
        )
        if match:
            await interaction.followup.send(
                "✅ Reprocesada con el lector nuevo y CARGADA: "
                f"**{match['home_team']} {match['home_goals']}–{match['away_goals']} {match['away_team']}**.",
                ephemeral=True,
            )
            return

        status = review_status or evidence_status or "SIN_RESULTADO"
        await interaction.followup.send(
            "⚠️ El lector nuevo procesó la captura pero NO cargó un partido oficial. "
            f"Estado: **{status}**. Mirá el mensaje público/Staff que generó el lector.",
            ephemeral=True,
        )
    except ValueError as exc:
        await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
    except Exception as exc:
        print(f"AJAP Liga rehabilitar captura error: {type(exc).__name__}: {exc}")
        await interaction.followup.send(
            f"❌ Falló el reproceso: {type(exc).__name__}: {str(exc)[:250]}",
            ephemeral=True,
        )


async def _sync_rehab_command_to_guilds():
    bot = BOT
    if bot is None or not bot.user:
        return
    for guild in list(bot.guilds):
        target = discord.Object(id=int(guild.id))
        try:
            bot.tree.add_command(rehabilitar_captura_prueba, guild=target, override=True)
            await bot.tree.sync(guild=target)
        except Exception as exc:
            print(f"ERROR AJAP Liga slash sync guild={getattr(guild, 'id', '?')}: {exc}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_league_capture_rehab_patch", False):
        return
    existing = bot.tree.get_command("rehabilitar_captura_prueba")
    if existing is not None:
        bot.tree.remove_command("rehabilitar_captura_prueba")
    bot.tree.add_command(rehabilitar_captura_prueba)
    if not getattr(bot, "_ajap_rehab_guild_sync_listener", False):
        bot.add_listener(_sync_rehab_command_to_guilds, "on_ready")
        bot._ajap_rehab_guild_sync_listener = True
    runtime._ajap_league_capture_rehab_patch = True
    print("AJAP Liga: /rehabilitar_captura_prueba usa el lector LIVE y verifica DB")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_rehab(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_league_capture_rehab_wrapped", False):
    _apply_guild_isolation_then_rehab._ajap_league_capture_rehab_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_rehab
