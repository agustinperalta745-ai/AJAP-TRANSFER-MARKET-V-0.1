"""Deep read-only integrity audit for AJAP Liga.

This command complements /auditar_resultados. It walks the configured Results
channel oldest-to-newest, re-reads every image message with the current local
Tesseract/PES6 reader, compares what the screenshot says with league_matches,
and independently rebuilds the standings from the official match rows.

It NEVER inserts, updates or deletes matches, goals, evidence, reviews or hashes.
"""
from __future__ import annotations

import mimetypes
from collections import defaultdict

import discord
from discord import app_commands

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_historical_audit_patch as hist
import league_multisignal_result_patch as multisignal

APP = None
BOT = None
_SYNCED = set()


def _images(message):
    out = []
    for att in message.attachments:
        mime = (att.content_type or mimetypes.guess_type(att.filename)[0] or "").split(";")[0]
        if mime.startswith("image/"):
            out.append((att, mime))
    return out


async def _image_payload(message):
    images = []
    for att, mime in _images(message)[: league.MAX_IMAGES]:
        try:
            if att.size and int(att.size) > league.MAX_BYTES:
                continue
            try:
                data = await att.read(use_cached=True)
            except TypeError:
                data = await att.read()
            if data:
                images.append((data, mime))
        except Exception:
            continue
    return images


def _same_result(read_score, match):
    if not read_score or match is None:
        return False
    rh, ra, rg_h, rg_a = read_score
    mh = str(match["home_team"])
    ma = str(match["away_team"])
    mg_h = int(match["home_goals"])
    mg_a = int(match["away_goals"])
    direct = (
        str(rh).casefold() == mh.casefold()
        and str(ra).casefold() == ma.casefold()
        and int(rg_h) == mg_h
        and int(rg_a) == mg_a
    )
    reverse = (
        str(rh).casefold() == ma.casefold()
        and str(ra).casefold() == mh.casefold()
        and int(rg_h) == mg_a
        and int(rg_a) == mg_h
    )
    return direct or reverse


def _score_text(score):
    if not score:
        return "no legible"
    h, a, hg, ag = score
    return f"{h} {int(hg)}–{int(ag)} {a}"


def _match_text(row):
    return f"{row['home_team']} {int(row['home_goals'])}–{int(row['away_goals'])} {row['away_team']}"


def _standings_from_matches(rows):
    table = {
        team: {"team": team, "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0}
        for team in league.TEAMS
    }
    for row in rows:
        h = table.get(str(row["home_team"]))
        a = table.get(str(row["away_team"]))
        if h is None or a is None:
            continue
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        h["pj"] += 1; a["pj"] += 1
        h["gf"] += hg; h["gc"] += ag
        a["gf"] += ag; a["gc"] += hg
        if hg > ag:
            h["pg"] += 1; a["pp"] += 1; h["pts"] += 3
        elif ag > hg:
            a["pg"] += 1; h["pp"] += 1; a["pts"] += 3
        else:
            h["pe"] += 1; a["pe"] += 1; h["pts"] += 1; a["pts"] += 1
    for item in table.values():
        item["dif"] = item["gf"] - item["gc"]
    return sorted(table.values(), key=lambda x: (-x["pts"], -x["dif"], -x["gf"], x["team"].casefold()))


async def _send_chunks(interaction, title, lines):
    if not lines:
        return
    chunk = f"**{title}**\n"
    for line in lines:
        if len(chunk) + len(line) + 1 > 1850:
            await interaction.followup.send(chunk, ephemeral=True)
            chunk = f"**{title} (continuación)**\n"
        chunk += line + "\n"
    if chunk.strip():
        await interaction.followup.send(chunk, ephemeral=True)


@app_commands.command(
    name="auditar_integridad",
    description="Relee todo Resultados y compara capturas, DB y tabla sin modificar nada.",
)
async def auditar_integridad(interaction: discord.Interaction):
    runtime = APP
    if runtime is None or not interaction.guild_id or interaction.guild is None:
        await interaction.response.send_message("⚠️ La Liga todavía no está lista.", ephemeral=True)
        return
    if not runtime.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return

    cfg = hist._config(runtime, interaction.guild_id)
    intake_id = int(cfg["intake_channel_id"]) if cfg and cfg["intake_channel_id"] else None
    if not intake_id:
        await interaction.response.send_message("⚠️ No hay canal de Resultados configurado.", ephemeral=True)
        return
    channel = interaction.guild.get_channel(intake_id)
    if channel is None:
        try:
            channel = await interaction.guild.fetch_channel(intake_id)
        except Exception:
            channel = None
    if channel is None or not hasattr(channel, "history"):
        await interaction.response.send_message("⚠️ No pude acceder al historial de Resultados.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    matches_by_source, scorer_totals, reviews, evidence, stored_hashes = hist._snapshot(runtime, interaction.guild_id)

    conn = league.db(runtime, interaction.guild_id)
    try:
        all_matches = conn.execute("SELECT * FROM league_matches ORDER BY id ASC").fetchall()
    finally:
        conn.close()

    total_images = 0
    linked_once = 0
    photo_verified = 0
    photo_unreadable = []
    photo_mismatch = []
    missing_db = []
    multi_db = []

    try:
        async for message in channel.history(limit=None, oldest_first=True):
            if not _images(message):
                continue
            total_images += 1
            rows = matches_by_source.get(int(message.id), [])
            if len(rows) == 1:
                linked_once += 1
            elif len(rows) == 0:
                missing_db.append(message)
            else:
                multi_db.append((message, rows))

            images = await _image_payload(message)
            if not images:
                photo_unreadable.append((message, None, rows[0] if len(rows) == 1 else None))
                continue
            try:
                payload = await multisignal.analyze_message(runtime, message, images)
                read_score = league.parsed_score(payload or {})
            except Exception as exc:
                print(f"AJAP integrity OCR message={message.id}: {type(exc).__name__}: {exc}")
                read_score = None

            if len(rows) == 1:
                if read_score is None:
                    photo_unreadable.append((message, None, rows[0]))
                elif _same_result(read_score, rows[0]):
                    photo_verified += 1
                else:
                    photo_mismatch.append((message, read_score, rows[0]))
            elif len(rows) == 0 and read_score is not None:
                # Keep the candidate only as audit output. Never persist it here.
                missing_db[-1] = (message, read_score)
    except discord.Forbidden:
        await interaction.followup.send("❌ Falta permiso para leer todo el historial de Resultados.", ephemeral=True)
        return
    except Exception as exc:
        await interaction.followup.send(f"❌ Auditoría interrumpida por `{type(exc).__name__}`.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🧪 CONTROL DE INTEGRIDAD • LIGA",
        description=(
            f"Recorrí {channel.mention} **desde el primer mensaje hasta el último** y releí las imágenes con el lector local actual.\n"
            "**Solo lectura:** no se cargó, borró ni corrigió ningún resultado."
        ),
        color=discord.Color.green() if not missing_db and not photo_mismatch and not multi_db else discord.Color.gold(),
    )
    embed.add_field(name="📸 Mensajes con imagen", value=str(total_images), inline=True)
    embed.add_field(name="✅ Vinculados 1 vez", value=str(linked_once), inline=True)
    embed.add_field(name="🔍 Foto = DB comprobado", value=str(photo_verified), inline=True)
    embed.add_field(name="⚠️ Sin partido en DB", value=str(len(missing_db)), inline=True)
    embed.add_field(name="🚨 Foto ≠ partido guardado", value=str(len(photo_mismatch)), inline=True)
    embed.add_field(name="👁️ No pude releer la foto", value=str(len(photo_unreadable)), inline=True)
    embed.add_field(name="🚨 >1 fila DB mismo mensaje", value=str(len(multi_db)), inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)

    missing_lines = []
    for item in missing_db:
        if isinstance(item, tuple):
            message, score = item
            missing_lines.append(f"• {_score_text(score)} — [mensaje]({message.jump_url})")
        else:
            missing_lines.append(f"• sin lectura concluyente — [mensaje]({item.jump_url})")
    mismatch_lines = [
        f"• FOTO: **{_score_text(score)}** • DB: **{_match_text(row)}** — [abrir]({message.jump_url})"
        for message, score, row in photo_mismatch
    ]
    unread_lines = [
        f"• DB: **{_match_text(row)}** — [foto]({message.jump_url})" if row is not None
        else f"• sin DB — [foto]({message.jump_url})"
        for message, _score, row in photo_unreadable
    ]
    await _send_chunks(interaction, "⚠️ CAPTURAS SIN PARTIDO GUARDADO", missing_lines)
    await _send_chunks(interaction, "🚨 CAPTURA Y DB NO COINCIDEN", mismatch_lines)
    await _send_chunks(interaction, "👁️ CAPTURAS QUE EL LECTOR ACTUAL NO PUDO VERIFICAR", unread_lines)

    standings = _standings_from_matches(all_matches)
    lines = []
    for pos, row in enumerate(standings, start=1):
        if row["pj"] <= 0:
            continue
        sign = "+" if row["dif"] > 0 else ""
        lines.append(
            f"{pos}. **{row['team']}** — PJ {row['pj']} • PG {row['pg']} • PE {row['pe']} • PP {row['pp']} • "
            f"GF {row['gf']} • GC {row['gc']} • DIF {sign}{row['dif']} • **{row['pts']} pts**"
        )
    await _send_chunks(interaction, "📊 TABLA RECONSTRUIDA DIRECTAMENTE DESDE league_matches", lines)

    scorer_missing = 0
    scorer_matches = 0
    for source_id, rows in matches_by_source.items():
        if len(rows) != 1:
            continue
        gap = hist._scorer_gap(rows[0], scorer_totals.get(int(source_id), {}))
        missing = int(gap["home_missing"]) + int(gap["away_missing"])
        if missing:
            scorer_matches += 1
            scorer_missing += missing
    await interaction.followup.send(
        f"⚽ Control de goleadores: **{scorer_matches} partido(s)** con faltantes, **{scorer_missing} gol(es)** todavía sin jugador asignado. "
        "Para corregirlos rápido usá `/auditar_resultados`, que deja las tarjetas con **COMPLETAR GOLEADORES**.",
        ephemeral=True,
    )


async def _sync():
    if BOT is None or not BOT.user:
        return
    for guild in list(BOT.guilds):
        if int(guild.id) in _SYNCED:
            continue
        target = discord.Object(id=int(guild.id))
        try:
            BOT.tree.add_command(auditar_integridad, guild=target, override=True)
            await BOT.tree.sync(guild=target)
            _SYNCED.add(int(guild.id))
        except Exception as exc:
            print(f"AJAP integrity audit sync guild={guild.id}: {type(exc).__name__}: {exc}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_integrity_audit", False):
        return
    existing = bot.tree.get_command("auditar_integridad")
    if existing is not None:
        try:
            bot.tree.remove_command("auditar_integridad")
        except Exception:
            pass
    try:
        bot.tree.add_command(auditar_integridad)
    except Exception as exc:
        print(f"AJAP integrity audit add: {type(exc).__name__}: {exc}")
    if not getattr(bot, "_ajap_integrity_audit_sync", False):
        bot.add_listener(_sync, "on_ready")
        bot._ajap_integrity_audit_sync = True
    runtime._ajap_integrity_audit = True
    print("AJAP Liga: auditoría profunda foto↔DB↔tabla ACTIVA")


_PREVIOUS = guild_isolation.apply_guild_isolation_patch

def _apply(runtime, bot):
    _PREVIOUS(runtime, bot)
    _install(runtime, bot)

if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_integrity_audit_wrapper", False):
    _apply._ajap_integrity_audit_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
