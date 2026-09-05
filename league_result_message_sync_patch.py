"""Keep public result replies synchronized with the official AJPA match row.

Staff corrections must not leave an old bot reply showing a false score/scorer
state. This layer edits the bot's own replies to the original screenshot after a
score/scorer correction and repairs stale recent replies on startup.
"""
from __future__ import annotations

import asyncio

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_persistent_result_correction_patch as tools

APP = None
BOT = None


def _scorer_state(runtime, guild_id: int, source_id: int, match):
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            """
            SELECT player, team, SUM(goals) AS goals
            FROM league_goal_events
            WHERE source_message_id=?
            GROUP BY player COLLATE NOCASE, COALESCE(team,'') COLLATE NOCASE
            ORDER BY team COLLATE NOCASE, goals DESC, player COLLATE NOCASE
            """,
            (int(source_id),),
        ).fetchall()
    finally:
        conn.close()

    grouped = {str(match['home_team']): [], str(match['away_team']): []}
    totals = {str(match['home_team']): 0, str(match['away_team']): 0}
    for row in rows:
        team = league.canonical_team(row['team']) or str(row['team'] or '')
        club = next((name for name in grouped if name.casefold() == str(team).casefold()), None)
        if not club:
            continue
        goals = int(row['goals'] or 0)
        player = str(row['player'] or '').strip()
        if player and goals > 0:
            grouped[club].append(f"{player}{f' x{goals}' if goals > 1 else ''}")
            totals[club] += goals

    pending = {
        str(match['home_team']): max(0, int(match['home_goals']) - totals[str(match['home_team'])]),
        str(match['away_team']): max(0, int(match['away_goals']) - totals[str(match['away_team'])]),
    }
    return grouped, pending


def _public_text(runtime, guild_id: int, source_id: int, match, corrected: bool):
    home = str(match['home_team'])
    away = str(match['away_team'])
    hg = int(match['home_goals'])
    ag = int(match['away_goals'])
    grouped, pending = _scorer_state(runtime, guild_id, source_id, match)

    title = "✅ **RESULTADO CORREGIDO POR STAFF**" if corrected else "✅ **RESULTADO OFICIAL ACTUALIZADO**"
    lines = [title, f"**{home} {hg}–{ag} {away}**"]
    for club in (home, away):
        if grouped[club]:
            lines.append(f"⚽ **{club}:** {', '.join(grouped[club])}")
    missing = [f"{club}: {count}" for club, count in pending.items() if count]
    if missing:
        lines.append("⚠️ **Goleadores pendientes:** " + " • ".join(missing))
    elif not grouped[home] and not grouped[away] and hg + ag:
        lines.append("⚠️ Goleadores todavía sin cargar.")
    lines.append("_Este mensaje refleja siempre el dato oficial de la Liga._")
    return "\n".join(lines), pending


def _message_blob(message: discord.Message) -> str:
    parts = [str(message.content or '')]
    for embed in message.embeds:
        parts.extend([str(embed.title or ''), str(embed.description or '')])
        for field in embed.fields:
            parts.extend([str(field.name or ''), str(field.value or '')])
    return " ".join(parts).casefold()


def _looks_like_result_reply(message: discord.Message) -> bool:
    blob = _message_blob(message)
    return any(word in blob for word in (
        'resultado', 'cargado', 'goleador', 'liga', 'validar', 'revisión', 'revision'
    ))


def _is_stale(message: discord.Message, match, pending) -> bool:
    blob = _message_blob(message)
    compact = blob.replace(' ', '').replace('–', '-').replace('—', '-')
    score = f"{int(match['home_goals'])}-{int(match['away_goals'])}"
    home_ok = str(match['home_team']).casefold() in blob
    away_ok = str(match['away_team']).casefold() in blob
    if score not in compact or not home_ok or not away_ok:
        return True
    says_pending = 'faltan goleadores' in blob or 'goleadores pendientes' in blob
    has_pending = any(int(value) > 0 for value in pending.values())
    if says_pending != has_pending:
        return True
    return False


async def sync_public_reply(guild: discord.Guild, source_id: int, *, corrected=False, force=False):
    runtime = APP or tools.APP
    bot = BOT or tools.BOT
    if runtime is None or bot is None or not bot.user:
        return 0
    match = tools._match(runtime, guild.id, int(source_id))
    if not match or not match['source_channel_id']:
        return 0
    channel = guild.get_channel(int(match['source_channel_id']))
    if channel is None:
        try:
            channel = await guild.fetch_channel(int(match['source_channel_id']))
        except Exception:
            return 0
    if not hasattr(channel, 'fetch_message') or not hasattr(channel, 'history'):
        return 0
    try:
        source = await channel.fetch_message(int(source_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return 0

    text, pending = _public_text(runtime, guild.id, int(source_id), match, corrected)
    changed = 0
    try:
        history = channel.history(limit=30, after=source, oldest_first=True)
        async for message in history:
            if not message.author or int(message.author.id) != int(bot.user.id):
                continue
            reference = getattr(message, 'reference', None)
            if not reference or int(getattr(reference, 'message_id', 0) or 0) != int(source_id):
                continue
            if not _looks_like_result_reply(message):
                continue
            if not force and not _is_stale(message, match, pending):
                continue
            try:
                await message.edit(content=text, embeds=[])
                changed += 1
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue
    except (discord.Forbidden, discord.HTTPException):
        return changed
    return changed


# Immediate synchronization after future Staff actions.
_original_correct_submit = tools.CorrectResultModal.on_submit
_original_scorer_submit = tools.ScorerEditModal.on_submit


async def _correct_submit(self, interaction: discord.Interaction):
    source_id = None
    if interaction.guild_id:
        runtime = APP or tools.APP
        if runtime is not None:
            try:
                row = tools._row_for_ges_message(runtime, interaction.guild_id, self.ges_message_id)
                source_id = int(row['source_message_id']) if row else None
            except Exception:
                source_id = None
    await _original_correct_submit(self, interaction)
    if source_id and interaction.guild:
        try:
            await sync_public_reply(interaction.guild, source_id, corrected=True, force=True)
        except Exception as exc:
            print(f"AJAP result public sync warning source={source_id}: {type(exc).__name__}: {exc}")


async def _scorer_submit(self, interaction: discord.Interaction):
    source_id = None
    if interaction.guild_id:
        runtime = APP or tools.APP
        if runtime is not None:
            try:
                row = tools._row_for_ges_message(runtime, interaction.guild_id, self.ges_message_id)
                source_id = int(row['source_message_id']) if row else None
            except Exception:
                source_id = None
    await _original_scorer_submit(self, interaction)
    if source_id and interaction.guild:
        try:
            await sync_public_reply(interaction.guild, source_id, corrected=True, force=True)
        except Exception as exc:
            print(f"AJAP scorer public sync warning source={source_id}: {type(exc).__name__}: {exc}")


if not getattr(tools.CorrectResultModal.on_submit, '_ajap_public_sync', False):
    _correct_submit._ajap_public_sync = True
    tools.CorrectResultModal.on_submit = _correct_submit
if not getattr(tools.ScorerEditModal.on_submit, '_ajap_public_sync', False):
    _scorer_submit._ajap_public_sync = True
    tools.ScorerEditModal.on_submit = _scorer_submit


async def _repair_recent_public_messages():
    # Let bounded DB repairs and normal ready hooks finish first.
    await asyncio.sleep(6)
    runtime = APP or tools.APP
    bot = BOT or tools.BOT
    if runtime is None or bot is None or not bot.user:
        return
    total = 0
    for guild in list(bot.guilds):
        conn = league.db(runtime, guild.id)
        try:
            rows = conn.execute(
                """
                SELECT source_message_id
                FROM league_matches
                WHERE source_message_id IS NOT NULL
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()
        finally:
            conn.close()
        for row in rows:
            try:
                total += await sync_public_reply(guild, int(row['source_message_id']), corrected=False, force=False)
            except Exception as exc:
                print(f"AJAP retro public sync warning source={row['source_message_id']}: {type(exc).__name__}: {exc}")
    print(f"AJAP Liga: mensajes públicos de resultados reparados={total}")


_PREVIOUS_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    global APP, BOT
    _PREVIOUS_APPLY(runtime, bot)
    APP, BOT = runtime, bot
    if getattr(bot, '_ajap_result_message_sync', False):
        return
    bot.add_listener(_repair_recent_public_messages, 'on_ready')
    bot._ajap_result_message_sync = True
    print('AJAP Liga: sincronización pública de resultados/correcciones activa')


if not getattr(guild_isolation.apply_guild_isolation_patch, '_ajap_result_message_sync_wrapper', False):
    _apply._ajap_result_message_sync_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
