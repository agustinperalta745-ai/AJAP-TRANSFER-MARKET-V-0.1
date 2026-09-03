"""Make missing scorer attribution explicit after an automatic AJAP result load."""
from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_result_feedback_patch as feedback
import league_validation_admin_review_patch as strict
import league_manual_scorer_entry_patch as entry
import league_manual_scorer_button_timeout_fix_patch as fast

_BASE_HANDLER = None
APP = None
BOT = None


def _match(runtime, guild_id, source_id):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute("SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1", (int(source_id),)).fetchone()
    finally:
        conn.close()


def _totals(runtime, guild_id, source_id):
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            "SELECT team, SUM(goals) AS goals FROM league_goal_events WHERE source_message_id=? GROUP BY team COLLATE NOCASE",
            (int(source_id),),
        ).fetchall()
        return {str(row["team"] or ""): int(row["goals"] or 0) for row in rows}
    finally:
        conn.close()


def _pending(runtime, guild_id, source_id):
    match = _match(runtime, guild_id, source_id)
    if not match:
        return None
    totals = _totals(runtime, guild_id, source_id)
    home = str(match["home_team"]); away = str(match["away_team"])
    mh = max(0, int(match["home_goals"]) - int(totals.get(home, 0)))
    ma = max(0, int(match["away_goals"]) - int(totals.get(away, 0)))
    return match, mh, ma


def _ensure_review(runtime, message, match):
    strict._ensure_schema(runtime, message.guild.id)
    conn = league.db(runtime, message.guild.id)
    try:
        conn.execute(
            """
            INSERT INTO league_manual_reviews
                (source_message_id,guild_id,source_channel_id,source_author_id,reason,status,
                 home_team,away_team,home_goals,away_goals,resolved_at)
            VALUES (?,?,?,?,?,'RESUELTO',?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(source_message_id) DO UPDATE SET
                reason=excluded.reason,
                status='RESUELTO',
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                home_goals=excluded.home_goals,
                away_goals=excluded.away_goals,
                resolved_at=COALESCE(league_manual_reviews.resolved_at,CURRENT_TIMESTAMP)
            """,
            (
                int(message.id), int(message.guild.id), int(message.channel.id), int(message.author.id),
                "Resultado oficial cargado; faltan goleadores por identificar.",
                str(match["home_team"]), str(match["away_team"]),
                int(match["home_goals"]), int(match["away_goals"]),
            ),
        )
        conn.commit()
        return conn.execute("SELECT * FROM league_manual_reviews WHERE source_message_id=?", (int(message.id),)).fetchone()
    finally:
        conn.close()


def _embed(runtime, guild_id, review):
    source_id = int(review["source_message_id"])
    pending = _pending(runtime, guild_id, source_id)
    match, mh, ma = pending if pending else (None, 0, 0)
    if match is None:
        return discord.Embed(title="⚠️ GOLEADORES PENDIENTES", color=discord.Color.gold()), mh, ma
    complete = mh == 0 and ma == 0
    embed = discord.Embed(
        title="✅ GOLEADORES COMPLETOS" if complete else "⚠️ GOLEADORES PENDIENTES",
        description=(
            f"Resultado oficial: **{match['home_team']} {int(match['home_goals'])}–{int(match['away_goals'])} {match['away_team']}**\n\n"
            + ("Todos los goles ya tienen jugador asignado." if complete else "El partido **ya está cargado**. Solo falta completar la atribución individual indicada abajo.")
        ),
        color=discord.Color.green() if complete else discord.Color.gold(),
    )
    embed.add_field(name="Goleadores", value=entry._scorers_text(runtime, guild_id, source_id)[:1024], inline=False)
    if not complete:
        lines = []
        if mh: lines.append(f"• **{match['home_team']}**: faltan **{mh}** gol(es) por atribuir")
        if ma: lines.append(f"• **{match['away_team']}**: faltan **{ma}** gol(es) por atribuir")
        embed.add_field(name="Pendiente", value="\n".join(lines), inline=False)
        embed.set_footer(text="Usá Agregar goleador; el total nunca puede superar el marcador oficial")
    return embed, mh, ma


async def _refresh_card(interaction, review):
    runtime = APP or entry.APP or strict._runtime()
    if runtime is None or not interaction.guild_id or interaction.message is None:
        return
    embed, mh, ma = _embed(runtime, interaction.guild_id, review)
    view = fast.FastManualScorerView() if (mh or ma) else None
    await interaction.message.edit(embed=embed, view=view)


async def _ensure_card(runtime, bot, message):
    pending = _pending(runtime, message.guild.id, message.id)
    if not pending:
        return
    match, mh, ma = pending
    if mh == 0 and ma == 0:
        return
    review = _ensure_review(runtime, message, match)
    embed, _, _ = _embed(runtime, message.guild.id, review)

    staff_message = None
    if review["staff_channel_id"] and review["staff_message_id"]:
        try:
            channel = message.guild.get_channel(int(review["staff_channel_id"])) or await message.guild.fetch_channel(int(review["staff_channel_id"]))
            staff_message = await channel.fetch_message(int(review["staff_message_id"]))
            await staff_message.edit(embed=embed, view=fast.FastManualScorerView())
        except Exception:
            staff_message = None

    created = False
    if staff_message is None:
        channel = strict._staff_channel(message.guild)
        if channel is None:
            return
        staff_message = await channel.send(embed=embed, view=fast.FastManualScorerView())
        strict._store_staff_message(runtime, message.guild.id, message.id, channel.id, staff_message.id)
        created = True

    if created:
        bits = []
        if mh: bits.append(f"{match['home_team']}: {mh}")
        if ma: bits.append(f"{match['away_team']}: {ma}")
        try:
            await message.reply(
                "⚠️ **Resultado cargado**, pero faltan goleadores por identificar: " + " • ".join(bits) + ". Staff recibió una tarjeta para completarlos.",
                mention_author=False,
            )
        except Exception:
            pass


async def _handle(runtime, bot, message):
    await _BASE_HANDLER(runtime, bot, message)
    try:
        await _ensure_card(runtime, bot, message)
    except Exception as exc:
        print(f"WARNING AJAP scorer pending message={getattr(message,'id','?')}: {type(exc).__name__}: {exc}")


def _install(runtime, bot):
    global APP, BOT, _BASE_HANDLER
    APP, BOT = runtime, bot
    entry._refresh_staff_card = _refresh_card
    current = feedback._ORIGINAL_HANDLE
    if current is not None and not getattr(current, "_ajap_scorer_pending", False):
        _BASE_HANDLER = current
        _handle._ajap_scorer_pending = True
        feedback._ORIGINAL_HANDLE = _handle
    print("AJAP Liga: aviso obligatorio de goleadores faltantes activo")


_PREVIOUS_APPLY = guild_isolation.apply_guild_isolation_patch

def _apply(runtime, bot):
    _PREVIOUS_APPLY(runtime, bot)
    _install(runtime, bot)

if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_scorer_pending_wrapper", False):
    _apply._ajap_scorer_pending_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
