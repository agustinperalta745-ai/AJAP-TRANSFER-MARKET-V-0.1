"""Read-only historical audit for AJAP result channel + fast scorer completion.

The audit walks the configured Results channel from oldest to newest and compares
Discord evidence with the guild league DB. It NEVER creates/deletes/changes an
official match or standings row.

It reports:
- image messages with exactly one official match;
- image messages with no official match linked to that Discord message;
- exact repeated image files (SHA-256) in the channel;
- scorer attribution totals vs each official score;
- anomalous over-attribution, if any.

For already-official matches with missing scorer attribution, Staff gets/refreshes
one compact correction card containing the original screenshot and a single
"COMPLETAR GOLEADORES" button. The modal accepts all missing scorers for both
clubs at once, e.g. ``Pauleta=2`` on separate lines. Player names are validated
against the registered roster and totals can never exceed the official score.

Blank PES6 scorer slots are intentionally ignored: only named, roster-resolved
players become league_goal_events.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
from collections import defaultdict

import discord
from discord import app_commands

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_manual_scorer_entry_patch as entry
import league_result_feedback_patch as feedback
import league_scorer_pending_patch as pending
import league_validation_admin_review_patch as strict


APP = None
BOT = None
_SYNCED_GUILDS = set()
PREFIX = "ajap:league:historical-audit:"


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _config(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            "SELECT * FROM league_config WHERE guild_id=? LIMIT 1",
            (int(guild_id),),
        ).fetchone()
    finally:
        conn.close()


def _snapshot(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        matches = defaultdict(list)
        if _table_exists(conn, "league_matches"):
            for row in conn.execute("SELECT * FROM league_matches ORDER BY id ASC").fetchall():
                matches[int(row["source_message_id"])].append(row)

        scorer_totals = defaultdict(lambda: defaultdict(int))
        if _table_exists(conn, "league_goal_events"):
            rows = conn.execute(
                """
                SELECT source_message_id, team, SUM(goals) AS goals
                FROM league_goal_events
                GROUP BY source_message_id, COALESCE(team,'') COLLATE NOCASE
                """
            ).fetchall()
            for row in rows:
                scorer_totals[int(row["source_message_id"])][str(row["team"] or "")] += int(row["goals"] or 0)

        reviews = {}
        if _table_exists(conn, "league_manual_reviews"):
            for row in conn.execute("SELECT * FROM league_manual_reviews").fetchall():
                reviews[int(row["source_message_id"])] = row

        evidence = {}
        if _table_exists(conn, "league_result_evidence"):
            for row in conn.execute("SELECT * FROM league_result_evidence").fetchall():
                evidence[int(row["source_message_id"])] = row

        stored_hashes = {}
        if _table_exists(conn, "league_image_hashes"):
            for row in conn.execute("SELECT image_hash,source_message_id FROM league_image_hashes").fetchall():
                stored_hashes[str(row["image_hash"])] = int(row["source_message_id"])

        return matches, scorer_totals, reviews, evidence, stored_hashes
    finally:
        conn.close()


def _image_attachments(message):
    out = []
    for att in message.attachments:
        mime = (att.content_type or mimetypes.guess_type(att.filename)[0] or "").split(";")[0]
        if mime.startswith("image/"):
            out.append(att)
    return out


async def _attachment_hashes(message):
    hashes = []
    for att in _image_attachments(message):
        try:
            if att.size and att.size > league.MAX_BYTES:
                continue
            data = await att.read(use_cached=True)
        except TypeError:
            try:
                data = await att.read()
            except Exception:
                continue
        except Exception:
            continue
        if data:
            hashes.append(hashlib.sha256(data).hexdigest())
    return hashes


def _team_total(totals, club: str) -> int:
    wanted = str(club or "").casefold()
    total = 0
    for team, goals in (totals or {}).items():
        canonical = league.canonical_team(team) or str(team or "")
        if canonical.casefold() == wanted:
            total += int(goals or 0)
    return total


def _scorer_gap(match, totals):
    home = str(match["home_team"])
    away = str(match["away_team"])
    assigned_h = _team_total(totals, home)
    assigned_a = _team_total(totals, away)
    score_h = int(match["home_goals"] or 0)
    score_a = int(match["away_goals"] or 0)
    return {
        "home_assigned": assigned_h,
        "away_assigned": assigned_a,
        "home_missing": max(0, score_h - assigned_h),
        "away_missing": max(0, score_a - assigned_a),
        "home_excess": max(0, assigned_h - score_h),
        "away_excess": max(0, assigned_a - score_a),
    }


def _parse_bulk(value: str):
    text = str(value or "").strip()
    if not text:
        return []
    pieces = [part.strip() for part in re.split(r"[\n;,]+", text) if part.strip()]
    out = []
    for piece in pieces:
        match = re.match(r"^(.+?)\s*(?:=|:|\bx\s*)(\d{1,2})\s*$", piece, flags=re.I)
        if not match:
            raise ValueError(
                f"No entendí `{piece}`. Usá una línea por jugador: `Jugador=2`."
            )
        name = match.group(1).strip()
        goals = int(match.group(2))
        if not name or goals < 1:
            raise ValueError(f"Entrada inválida: `{piece}`.")
        out.append((name, goals))
    return out


def _bulk_resolve(runtime, guild_id: int, review, home_entries, away_entries):
    resolved = []
    for side, club, items in (
        ("home", str(review["home_team"]), home_entries),
        ("away", str(review["away_team"]), away_entries),
    ):
        seen = set()
        for raw_name, goals in items:
            player = entry._resolve_roster_player(runtime, int(guild_id), club, raw_name)
            if not player:
                raise ValueError(
                    f"No encontré **{raw_name}** en la plantilla registrada de **{club}**."
                )
            key = league.norm(player)
            if key in seen:
                raise ValueError(f"**{player}** está repetido en la carga de {club}.")
            seen.add(key)
            resolved.append((side, club, player, int(goals)))
    return resolved


def _bulk_upsert(runtime, guild_id: int, review, resolved):
    source_id = int(review["source_message_id"])
    home = str(review["home_team"])
    away = str(review["away_team"])
    limits = {
        home.casefold(): int(review["home_goals"] or 0),
        away.casefold(): int(review["away_goals"] or 0),
    }

    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT id,player,team,goals FROM league_goal_events WHERE source_message_id=?",
            (source_id,),
        ).fetchall()

        # Proposed totals start from existing rows, then entries in this modal
        # replace the total for the same player+club instead of adding another row.
        proposed = {}
        ids = defaultdict(list)
        for row in existing:
            club = str(row["team"] or "")
            player = str(row["player"] or "")
            key = (club.casefold(), league.norm(player))
            proposed[key] = proposed.get(key, 0) + int(row["goals"] or 0)
            ids[key].append(int(row["id"]))

        for _side, club, player, goals in resolved:
            proposed[(club.casefold(), league.norm(player))] = int(goals)

        totals = defaultdict(int)
        for (club_key, _player_key), goals in proposed.items():
            totals[club_key] += int(goals)
        for club_key, limit in limits.items():
            if totals[club_key] > int(limit):
                club = home if club_key == home.casefold() else away
                raise ValueError(
                    f"Los goleadores de **{club}** sumarían {totals[club_key]}, "
                    f"pero el resultado oficial tiene {limit}."
                )

        for _side, club, player, goals in resolved:
            key = (club.casefold(), league.norm(player))
            same_ids = ids.get(key, [])
            if same_ids:
                keep = same_ids[0]
                conn.execute(
                    "UPDATE league_goal_events SET player=?,team=?,goals=?,confidence=1.0 WHERE id=?",
                    (player, club, int(goals), keep),
                )
                for extra_id in same_ids[1:]:
                    conn.execute("DELETE FROM league_goal_events WHERE id=?", (extra_id,))
            else:
                conn.execute(
                    """
                    INSERT INTO league_goal_events
                        (source_message_id,player,team,goals,confidence)
                    VALUES (?,?,?,?,1.0)
                    """,
                    (source_id, player, club, int(goals)),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _review_from_staff(runtime, guild_id: int, staff_message_id: int):
    return entry._review(runtime, int(guild_id), int(staff_message_id))


def _correction_embed(runtime, guild_id: int, review, source=None):
    source_id = int(review["source_message_id"])
    match = pending._match(runtime, int(guild_id), source_id)
    if not match:
        return discord.Embed(
            title="⚠️ AUDITORÍA • RESULTADO NO ENCONTRADO",
            color=discord.Color.gold(),
        ), 0, 0

    current = pending._pending(runtime, int(guild_id), source_id)
    _m, mh, ma = current if current else (match, 0, 0)
    complete = mh == 0 and ma == 0
    embed = discord.Embed(
        title="✅ AUDITORÍA • GOLEADORES COMPLETOS" if complete else "⚠️ AUDITORÍA • FALTAN GOLEADORES",
        description=(
            f"Resultado oficial: **{match['home_team']} {int(match['home_goals'])}–"
            f"{int(match['away_goals'])} {match['away_team']}**\n\n"
            + (
                "Todos los goles ya tienen un jugador asignado."
                if complete
                else "El resultado **ya está cargado**. Solo falta completar nombres de goleadores."
            )
        ),
        color=discord.Color.green() if complete else discord.Color.gold(),
    )
    embed.add_field(
        name="Goleadores cargados",
        value=entry._scorers_text(runtime, int(guild_id), source_id)[:1024],
        inline=False,
    )
    if not complete:
        lines = []
        if mh:
            lines.append(f"• **{match['home_team']}**: faltan **{mh}** gol(es)")
        if ma:
            lines.append(f"• **{match['away_team']}**: faltan **{ma}** gol(es)")
        embed.add_field(name="Falta atribuir", value="\n".join(lines), inline=False)
        embed.add_field(
            name="Carga rápida",
            value="Tocá **COMPLETAR GOLEADORES** y cargá todos juntos como `Jugador=2`, una línea por jugador.",
            inline=False,
        )
    if source is not None:
        embed.add_field(
            name="Captura original",
            value=f"[Abrir mensaje en Resultados]({source.jump_url})",
            inline=False,
        )
        first = next(iter(_image_attachments(source)), None)
        if first is not None:
            embed.set_image(url=first.url)
    embed.set_footer(text="Los slots vacíos de PES6 no se cargan como jugadores")
    return embed, mh, ma


class BulkScorersModal(discord.ui.Modal):
    def __init__(self, staff_message_id: int, review, mh: int, ma: int):
        super().__init__(title="Completar goleadores")
        self.staff_message_id = int(staff_message_id)
        home_label = f"{review['home_team']} • faltan {mh}"[:45]
        away_label = f"{review['away_team']} • faltan {ma}"[:45]
        self.home_entries = discord.ui.TextInput(
            label=home_label,
            placeholder="Ej: Pauleta=2\nRonaldinho=1",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500,
        )
        self.away_entries = discord.ui.TextInput(
            label=away_label,
            placeholder="Ej: Babel=2",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500,
        )
        self.add_item(self.home_entries)
        self.add_item(self.away_entries)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        runtime = APP or strict._runtime()
        if runtime is None or not interaction.guild_id:
            await interaction.followup.send("⚠️ No pude acceder a la Liga.", ephemeral=True)
            return
        if not runtime.es_admin(interaction):
            await interaction.followup.send("⛔ Solo administradores.", ephemeral=True)
            return

        review = _review_from_staff(runtime, interaction.guild_id, self.staff_message_id)
        if not review or str(review["status"] or "").upper() != "RESUELTO":
            await interaction.followup.send(
                "⚠️ Esta tarjeta ya no está disponible para completar goleadores.",
                ephemeral=True,
            )
            return

        try:
            home_entries = _parse_bulk(self.home_entries.value)
            away_entries = _parse_bulk(self.away_entries.value)
            if not home_entries and not away_entries:
                raise ValueError("No cargaste ningún jugador.")
            resolved = _bulk_resolve(
                runtime, interaction.guild_id, review, home_entries, away_entries
            )
            _bulk_upsert(runtime, interaction.guild_id, review, resolved)
        except ValueError as exc:
            await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
            return
        except Exception as exc:
            print(f"AJAP audit bulk scorers: {type(exc).__name__}: {exc}")
            await interaction.followup.send(
                "❌ No pude guardar esa carga. No se modificó el resultado oficial.",
                ephemeral=True,
            )
            return

        try:
            await league.refresh(runtime, BOT or interaction.client, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP audit scorer refresh: {type(exc).__name__}: {exc}")

        try:
            source = None
            if interaction.guild:
                channel = interaction.guild.get_channel(int(review["source_channel_id"]))
                if channel is None:
                    channel = await interaction.guild.fetch_channel(int(review["source_channel_id"]))
                source = await channel.fetch_message(int(review["source_message_id"]))
            embed, mh, ma = _correction_embed(runtime, interaction.guild_id, review, source)
            await interaction.message.edit(
                embed=embed,
                view=AuditScorerView() if (mh or ma) else None,
            )
        except Exception as exc:
            print(f"AJAP audit scorer card refresh: {type(exc).__name__}: {exc}")

        names = ", ".join(f"{player} x{goals}" for _s, _c, player, goals in resolved)
        await interaction.followup.send(
            f"✅ Goleadores guardados: **{names}**.", ephemeral=True
        )


class AuditScorerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="COMPLETAR GOLEADORES",
        emoji="⚽",
        style=discord.ButtonStyle.primary,
        custom_id=PREFIX + "bulk-scorers",
    )
    async def bulk(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = APP or strict._runtime()
        if runtime is None or not interaction.guild_id or interaction.message is None:
            return
        if not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        review = _review_from_staff(runtime, interaction.guild_id, interaction.message.id)
        if not review:
            await interaction.response.send_message(
                "⚠️ No pude vincular esta tarjeta con el partido.", ephemeral=True
            )
            return
        current = pending._pending(runtime, interaction.guild_id, int(review["source_message_id"]))
        if not current:
            await interaction.response.send_message(
                "ℹ️ Ese resultado ya no tiene goleadores pendientes.", ephemeral=True
            )
            return
        _match, mh, ma = current
        if mh == 0 and ma == 0:
            await interaction.response.send_message(
                "✅ Todos los goleadores ya están completos.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            BulkScorersModal(interaction.message.id, review, mh, ma)
        )


async def _ensure_correction_card(runtime, bot, source, match):
    current = pending._pending(runtime, source.guild.id, source.id)
    if not current:
        return False
    _match, mh, ma = current
    if mh == 0 and ma == 0:
        return False

    review = pending._ensure_review(runtime, source, match)
    embed, mh, ma = _correction_embed(runtime, source.guild.id, review, source)
    staff_message = None

    if review["staff_channel_id"] and review["staff_message_id"]:
        try:
            channel = source.guild.get_channel(int(review["staff_channel_id"]))
            if channel is None:
                channel = await source.guild.fetch_channel(int(review["staff_channel_id"]))
            staff_message = await channel.fetch_message(int(review["staff_message_id"]))
            await staff_message.edit(embed=embed, view=AuditScorerView())
        except Exception:
            staff_message = None

    if staff_message is None:
        channel = strict._staff_channel(source.guild)
        if channel is None:
            return False
        staff_message = await channel.send(embed=embed, view=AuditScorerView())
        strict._store_staff_message(
            runtime, source.guild.id, source.id, channel.id, staff_message.id
        )
    return True


def _status_text(review, evidence):
    if review is not None:
        return f"revisión `{str(review['status'] or 'PENDIENTE')}`"
    if evidence is not None:
        return f"evidencia `{str(evidence['status'] or 'SIN_ESTADO')}`"
    return "sin registro de revisión/evidencia"


async def _send_chunks(interaction, title: str, lines):
    if not lines:
        return
    chunk = f"**{title}**\n"
    for line in lines:
        candidate = chunk + line + "\n"
        if len(candidate) > 1850:
            await interaction.followup.send(chunk, ephemeral=True)
            chunk = f"**{title} (continuación)**\n{line}\n"
        else:
            chunk = candidate
    if chunk.strip():
        await interaction.followup.send(chunk, ephemeral=True)


@app_commands.command(
    name="auditar_resultados",
    description="Revisa todo el historial del canal Resultados sin modificar partidos.",
)
async def auditar_resultados(interaction: discord.Interaction):
    runtime = APP
    bot = BOT or interaction.client
    if runtime is None or not interaction.guild_id or interaction.guild is None:
        await interaction.response.send_message("⚠️ La Liga todavía no está lista.", ephemeral=True)
        return
    if not runtime.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return

    cfg = _config(runtime, interaction.guild_id)
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
        await interaction.response.send_message("⚠️ No pude acceder al historial del canal Resultados.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    matches, scorer_totals, reviews, evidence, stored_hashes = _snapshot(
        runtime, interaction.guild_id
    )

    total_images = 0
    loaded_once = 0
    missing_official = []
    scorer_incomplete = []
    scorer_excess = []
    multi_source_match = []
    exact_reposts = []
    hash_messages = defaultdict(list)
    correction_cards = 0

    try:
        async for message in channel.history(limit=None, oldest_first=True):
            images = _image_attachments(message)
            if not images:
                continue
            total_images += 1

            digests = await _attachment_hashes(message)
            for digest in digests:
                hash_messages[digest].append(message)

            rows = matches.get(int(message.id), [])
            if len(rows) == 1:
                loaded_once += 1
                match = rows[0]
                gap = _scorer_gap(match, scorer_totals.get(int(message.id), {}))
                if gap["home_excess"] or gap["away_excess"]:
                    scorer_excess.append((message, match, gap))
                if gap["home_missing"] or gap["away_missing"]:
                    scorer_incomplete.append((message, match, gap))
                    try:
                        if await _ensure_correction_card(runtime, bot, message, match):
                            correction_cards += 1
                    except Exception as exc:
                        print(
                            f"AJAP audit correction card source={message.id}: "
                            f"{type(exc).__name__}: {exc}"
                        )
            elif len(rows) > 1:
                multi_source_match.append((message, rows))
            else:
                missing_official.append(
                    (message, reviews.get(int(message.id)), evidence.get(int(message.id)), digests)
                )
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ El bot no tiene permiso para leer todo el historial de Resultados.",
            ephemeral=True,
        )
        return
    except Exception as exc:
        print(f"AJAP historical audit: {type(exc).__name__}: {exc}")
        await interaction.followup.send(
            f"❌ La auditoría se interrumpió por `{type(exc).__name__}`.", ephemeral=True
        )
        return

    for digest, messages in hash_messages.items():
        if len(messages) > 1:
            exact_reposts.append((digest, messages, stored_hashes.get(digest)))

    missing_goal_count = sum(
        int(gap["home_missing"]) + int(gap["away_missing"])
        for _message, _match, gap in scorer_incomplete
    )

    summary = discord.Embed(
        title="🔎 AUDITORÍA HISTÓRICA • RESULTADOS",
        description=(
            f"Canal revisado completo: {channel.mention}\n"
            "La auditoría **no modificó ningún resultado oficial ni la tabla**."
        ),
        color=discord.Color.green()
        if not missing_official and not scorer_excess and not multi_source_match
        else discord.Color.gold(),
    )
    summary.add_field(name="📸 Mensajes con imágenes", value=str(total_images), inline=True)
    summary.add_field(name="✅ Con 1 resultado oficial", value=str(loaded_once), inline=True)
    summary.add_field(name="⚠️ Sin resultado vinculado", value=str(len(missing_official)), inline=True)
    summary.add_field(name="⚽ Partidos con goleadores incompletos", value=str(len(scorer_incomplete)), inline=True)
    summary.add_field(name="🥅 Goles todavía sin jugador", value=str(missing_goal_count), inline=True)
    summary.add_field(name="🧾 Tarjetas rápidas Staff", value=str(correction_cards), inline=True)
    summary.add_field(name="♻️ Reenvíos exactos de la misma imagen", value=str(len(exact_reposts)), inline=True)
    summary.add_field(name="🚨 Exceso de goles atribuidos", value=str(len(scorer_excess)), inline=True)
    summary.add_field(name="🚨 Más de 1 partido en un mismo mensaje", value=str(len(multi_source_match)), inline=True)
    summary.set_footer(text="Slots vacíos de PES6 no cuentan como goleadores")
    await interaction.followup.send(embed=summary, ephemeral=True)

    missing_lines = []
    for message, review, ev, digests in missing_official:
        hash_note = ""
        linked_elsewhere = sorted(
            {
                stored_hashes[d]
                for d in digests
                if d in stored_hashes and int(stored_hashes[d]) != int(message.id)
            }
        )
        if linked_elsewhere:
            hash_note = " • misma imagen vinculada a otro mensaje"
        missing_lines.append(
            f"• [mensaje {message.id}]({message.jump_url}) — {_status_text(review, ev)}{hash_note}"
        )

    scorer_lines = []
    for message, match, gap in scorer_incomplete:
        bits = []
        if gap["home_missing"]:
            bits.append(f"{match['home_team']}: {gap['home_missing']}")
        if gap["away_missing"]:
            bits.append(f"{match['away_team']}: {gap['away_missing']}")
        scorer_lines.append(
            f"• **{match['home_team']} {int(match['home_goals'])}–{int(match['away_goals'])} {match['away_team']}** "
            f"— faltan {' • '.join(bits)} — [abrir captura]({message.jump_url})"
        )

    repost_lines = []
    for _digest, messages, stored_source in exact_reposts:
        links = " • ".join(f"[msg {m.id}]({m.jump_url})" for m in messages[:6])
        suffix = f" • DB vinculada a `{stored_source}`" if stored_source else ""
        repost_lines.append(f"• {links}{suffix}")

    excess_lines = []
    for message, match, gap in scorer_excess:
        bits = []
        if gap["home_excess"]:
            bits.append(f"{match['home_team']} +{gap['home_excess']}")
        if gap["away_excess"]:
            bits.append(f"{match['away_team']} +{gap['away_excess']}")
        excess_lines.append(
            f"• **{match['home_team']} {int(match['home_goals'])}–{int(match['away_goals'])} {match['away_team']}** "
            f"— exceso {' • '.join(bits)} — [abrir]({message.jump_url})"
        )

    await _send_chunks(interaction, "⚠️ IMÁGENES SIN RESULTADO OFICIAL VINCULADO", missing_lines)
    await _send_chunks(interaction, "⚽ GOLEADORES QUE FALTAN", scorer_lines)
    await _send_chunks(interaction, "♻️ MISMA IMAGEN PUBLICADA MÁS DE UNA VEZ", repost_lines)
    await _send_chunks(interaction, "🚨 GOLEADORES QUE SUPERAN EL MARCADOR", excess_lines)

    if scorer_incomplete:
        await interaction.followup.send(
            "✅ Para los partidos con goleadores faltantes dejé/actualicé tarjetas en Staff. "
            "Cada tarjeta trae la captura original y **COMPLETAR GOLEADORES** para cargar varios jugadores juntos.",
            ephemeral=True,
        )


async def _sync_command_to_guilds():
    bot = BOT
    if bot is None or not bot.user:
        return
    for guild in list(bot.guilds):
        if int(guild.id) in _SYNCED_GUILDS:
            continue
        target = discord.Object(id=int(guild.id))
        try:
            bot.tree.add_command(auditar_resultados, guild=target, override=True)
            await bot.tree.sync(guild=target)
            _SYNCED_GUILDS.add(int(guild.id))
            print(f"AJAP Liga audit slash sync guild={guild.id}: OK")
        except Exception as exc:
            print(f"AJAP Liga audit slash sync guild={guild.id}: {type(exc).__name__}: {exc}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_historical_audit_patch", False):
        return

    try:
        bot.add_view(AuditScorerView())
    except Exception as exc:
        print(f"AJAP Liga audit persistent view: {type(exc).__name__}: {exc}")

    existing = bot.tree.get_command("auditar_resultados")
    if existing is not None:
        try:
            bot.tree.remove_command("auditar_resultados")
        except Exception:
            pass
    try:
        bot.tree.add_command(auditar_resultados)
    except Exception as exc:
        print(f"AJAP Liga audit command add: {type(exc).__name__}: {exc}")

    if not getattr(bot, "_ajap_historical_audit_sync_listener", False):
        bot.add_listener(_sync_command_to_guilds, "on_ready")
        bot._ajap_historical_audit_sync_listener = True

    runtime._ajap_historical_audit_patch = True
    print("AJAP Liga: auditoría histórica + carga masiva de goleadores ACTIVA")


_PREVIOUS_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _PREVIOUS_APPLY(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_historical_audit_wrapper", False):
    _apply._ajap_historical_audit_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
