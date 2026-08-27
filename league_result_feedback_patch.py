"""Visible feedback guard for AJAP Liga result uploads.

The evidence workflow is intentionally strict, but an ignored/misconfigured channel
used to look exactly like a broken bot. This final wrapper guarantees visible
feedback around image uploads without changing the evidence rules:
- warn in channels named like "resultados" when they are not the configured intake;
- add an immediate hourglass while a configured screenshot is being processed;
- leave a lightweight reaction that reflects partial/review/pending state;
- expose /liga_diagnostico so Staff can inspect the live Discord runtime.
"""

from __future__ import annotations

import os
import sys
import unicodedata

import discord
from discord.ext import commands

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
    if not message.guild or message.author.bot:
        return await _ORIGINAL_HANDLE(runtime, bot, message)

    cfg = _config(runtime, message.guild.id)
    intake_id = int(cfg["intake_channel_id"]) if cfg and cfg["intake_channel_id"] else None

    # If Discord delivered the message event but hid the attachment payload, do
    # not look broken: make that state visible in a results-looking channel.
    if not message.attachments:
        if _looks_like_results_channel(message.channel) and not str(message.content or "").strip():
            await _safe_react(message, "⚠️")
            try:
                await message.reply(
                    "⚠️ Recibí el mensaje, pero Discord no me entregó ningún adjunto visible. "
                    "Usá `/liga_diagnostico` para revisar intents y permisos del bot.",
                    mention_author=False,
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
        return await _ORIGINAL_HANDLE(runtime, bot, message)

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


def _is_admin(runtime, interaction) -> bool:
    try:
        return bool(runtime.es_admin(interaction))
    except Exception:
        return bool(
            interaction.guild
            and isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.administrator
        )


def _staff_channel_id_for_guild(runtime, guild_id: int):
    """Read Staff/PES channel from the explicit guild DB, never the legacy context."""
    conn = None
    try:
        if hasattr(runtime, "db_for_guild"):
            conn = runtime.db_for_guild(int(guild_id))
        else:
            with runtime.guild_context(int(guild_id)) if hasattr(runtime, "guild_context") else _nullcontext():
                conn = runtime.db()
        row = conn.execute(
            "SELECT channel_id FROM market_report_channels WHERE guild_id = ? LIMIT 1",
            (int(guild_id),),
        ).fetchone()
        return int(row["channel_id"]) if row and row["channel_id"] else None
    except Exception:
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


class _nullcontext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _install_diagnostic_command(runtime, bot):
    if bot.tree.get_command("liga_diagnostico") is not None:
        return

    @bot.tree.command(
        name="liga_diagnostico",
        description="Diagnostica el lector automático de resultados de Liga",
    )
    async def liga_diagnostico(interaction: discord.Interaction):
        if not _is_admin(runtime, interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        if not interaction.guild_id:
            await interaction.response.send_message("⚠️ Usalo dentro del servidor.", ephemeral=True)
            return

        cfg = _config(runtime, interaction.guild_id)
        intake_id = int(cfg["intake_channel_id"]) if cfg and cfg["intake_channel_id"] else None
        listener_count = len(getattr(bot, "extra_events", {}).get("on_message", []))
        handler_name = getattr(league.handle, "__name__", type(league.handle).__name__)
        msg_intent = bool(getattr(bot.intents, "message_content", False))
        guild_msg_intent = bool(getattr(bot.intents, "guild_messages", False))
        api_value = os.getenv("OPENAI_API_KEY") or ""
        api_ok = bool(api_value)
        openai_env_names = sorted(name for name in os.environ if name.upper().startswith("OPENAI"))
        deployment_id = os.getenv("RAILWAY_DEPLOYMENT_ID") or "—"
        service_name = os.getenv("RAILWAY_SERVICE_NAME") or "—"
        commit_sha = (
            os.getenv("RAILWAY_GIT_COMMIT_SHA")
            or os.getenv("RAILWAY_GIT_COMMIT")
            or "—"
        )
        staff_id = _staff_channel_id_for_guild(runtime, interaction.guild_id)

        target = interaction.guild.get_channel(intake_id) if intake_id else None
        staff_target = interaction.guild.get_channel(staff_id) if staff_id else None
        me = interaction.guild.me
        perms = target.permissions_for(me) if target is not None and me is not None else None

        def ok(value):
            return "✅" if value else "❌"

        channel_text = target.mention if target is not None else (f"<#{intake_id}> (no accesible)" if intake_id else "Sin configurar")
        staff_text = staff_target.mention if staff_target is not None else (f"<#{staff_id}> (no accesible)" if staff_id else "Sin configurar")
        perm_text = "No se pudo comprobar"
        if perms is not None:
            perm_text = (
                f"{ok(perms.view_channel)} Ver canal • "
                f"{ok(perms.read_message_history)} Historial • "
                f"{ok(perms.send_messages)} Enviar • "
                f"{ok(perms.add_reactions)} Reaccionar"
            )

        healthy_handler = handler_name == "_feedback_handle"
        embed = discord.Embed(
            title="🧪 Diagnóstico Liga AJAP",
            description="Estado real del proceso que respondió este comando.",
            color=discord.Color.green() if (msg_intent and guild_msg_intent and listener_count > 0 and healthy_handler and intake_id and api_ok) else discord.Color.gold(),
        )
        embed.add_field(name="Message Content", value=f"{ok(msg_intent)} `{msg_intent}`", inline=True)
        embed.add_field(name="Guild Messages", value=f"{ok(guild_msg_intent)} `{guild_msg_intent}`", inline=True)
        embed.add_field(name="OPENAI_API_KEY", value=f"{ok(api_ok)} {'configurada' if api_ok else 'faltante'} • largo `{len(api_value)}`", inline=True)
        embed.add_field(name="Variables OPENAI recibidas", value="`, `".join(openai_env_names) if openai_env_names else "**ninguna**", inline=False)
        embed.add_field(name="Listeners on_message", value=f"{ok(listener_count > 0)} **{listener_count}**", inline=True)
        embed.add_field(name="Handler Liga", value=f"{ok(healthy_handler)} `{handler_name}`", inline=True)
        embed.add_field(name="PID proceso", value=f"`{os.getpid()}`", inline=True)
        embed.add_field(name="Canal Resultados", value=channel_text, inline=True)
        embed.add_field(name="Canal Staff/PES", value=staff_text, inline=True)
        embed.add_field(name="Servicio Railway", value=f"`{service_name}`", inline=True)
        embed.add_field(name="Deployment", value=f"`{deployment_id[-12:] if deployment_id != '—' else deployment_id}`", inline=True)
        embed.add_field(name="Commit", value=f"`{commit_sha[:10] if commit_sha != '—' else commit_sha}`", inline=True)
        embed.add_field(name="Permisos en Resultados", value=perm_text, inline=False)
        embed.set_footer(text="AJAP Liga diagnóstico v3 • no muestra valores secretos")
        await interaction.response.send_message(embed=embed, ephemeral=True)


def apply_league_result_feedback_patch(runtime, bot):
    global APP, BOT, _ORIGINAL_HANDLE
    APP, BOT = runtime, bot
    _install_diagnostic_command(runtime, bot)
    if getattr(runtime, "_ajap_league_result_feedback_patch", False):
        if _ORIGINAL_HANDLE is not None:
            league.handle = _feedback_handle
        return

    _ORIGINAL_HANDLE = league.handle
    league.handle = _feedback_handle
    runtime._ajap_league_result_feedback_patch = True
    print("AJAP Liga feedback visible activo: canal + procesamiento + estados + diagnostico v3")


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


_original_bot_run = commands.Bot.run


def _run_with_league_listener_guard(self, token, *args, **kwargs):
    runtime = sys.modules.get("ajap_bot_runtime")
    if runtime is not None:
        try:
            league.apply_league_automation_patch(runtime, self)

            import league_result_evidence_patch as evidence
            evidence._install(runtime, self)

            apply_league_result_feedback_patch(runtime, self)
            league.handle = _feedback_handle

            print("AJAP Liga listener verificado justo antes de conectar Discord")
        except Exception as exc:
            print(f"ERROR AJAP Liga listener guard: {exc}")
    return _original_bot_run(self, token, *args, **kwargs)


if not getattr(commands.Bot.run, "_ajap_league_listener_guard", False):
    _run_with_league_listener_guard._ajap_league_listener_guard = True
    commands.Bot.run = _run_with_league_listener_guard
