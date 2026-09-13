"""Radio Pasillo finalization announcements for official AJPA competitions.

Official season close:
- detects the real transition out of the `season` phase (mobile or Discord Staff),
- reads the frozen final snapshot created by competition_cycle,
- posts champion, final table and top scorer (player/goals/team/DT).

Champions/Europa close:
- consumes the persistent events queued by mobile_cup_admin_reset_finalize_patch,
- posts each champion and DT once when Staff explicitly finalizes that cup.

All jobs are persisted and retried. A small watcher also makes mobile finalization
appear in Radio Pasillo without waiting for a later GES refresh or bot restart.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import discord

import competition_cycle as cycle
import league_automation_patch as league
import league_top5_overtake_radio_patch as radio
import radio_pasillo_preseason_final_announcement_patch as final_base

_BASE_ADVANCE = cycle.advance
_BASE_REFRESH = league.refresh
_SEASON_EVENTS = "radio_pasillo_official_season_final_events"
_CUP_EVENTS = "radio_pasillo_cup_final_events"


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)).fetchone())


def _ensure_schema(conn) -> None:
    cycle.ensure_schema(conn)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SEASON_EVENTS} (
            competition_id INTEGER PRIMARY KEY,
            season_number INTEGER NOT NULL,
            guild_id INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            channel_id INTEGER,
            discord_message_id INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            posted_at DATETIME
        )
        """
    )
    conn.commit()


def _advance_with_final_event(conn, user_id, expected_phase=None):
    _ensure_schema(conn)
    before = conn.execute("SELECT phase,season_number,competition_id FROM competition_cycle_state WHERE id=1").fetchone()
    old_phase = str(before["phase"] or "") if before else ""
    old_season = int(before["season_number"] or 1) if before else 1
    old_cid = int(before["competition_id"]) if before and before["competition_id"] is not None else None

    result = _BASE_ADVANCE(conn, user_id, expected_phase)

    if old_phase == cycle.SEASON and old_cid is not None:
        conn.execute(
            f"""INSERT OR IGNORE INTO {_SEASON_EVENTS}
                   (competition_id,season_number,guild_id,status)
               VALUES(?,?,0,'pending')""",
            (old_cid, old_season),
        )
        conn.commit()
    return result


if not getattr(cycle, "_ajpa_radio_final_advance_wrapped", False):
    cycle.advance = _advance_with_final_event
    cycle._ajpa_radio_final_advance_wrapped = True


def _snapshot(conn, competition_id: int) -> tuple[dict[str, Any], str | None]:
    row = conn.execute(
        "SELECT ended_at,final_snapshot_json FROM competition_editions WHERE id=? LIMIT 1",
        (int(competition_id),),
    ).fetchone()
    if not row:
        return {}, None
    raw = str(row["final_snapshot_json"] or "").strip()
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}, (str(row["ended_at"] or "").strip() or None)


def _compact_table(standings: list[dict[str, Any]]) -> str:
    lines = ["#  EQUIPO                 PJ   DG   PTS"]
    for index, raw in enumerate(standings, start=1):
        row = final_base._row(dict(raw))
        name = str(row["team"] or "")[:20]
        dg = int(row["dg"])
        dg_text = f"+{dg}" if dg > 0 else str(dg)
        lines.append(f"{index:02d} {name:<20} {int(row['pj']):>2} {dg_text:>4} {int(row['pts']):>5}")
    return "```\n" + "\n".join(lines) + "\n```"


def _season_text(guild, season_number: int, standings: list[dict[str, Any]], scorers: list[dict[str, Any]], champion_dt, scorer_dt) -> str:
    champion = final_base._row(dict(standings[0]))
    golden = dict(scorers[0])
    champion_team = discord.utils.escape_markdown(str(champion.get("team") or ""))
    player = discord.utils.escape_markdown(str(golden.get("player") or ""))
    scorer_team = discord.utils.escape_markdown(str(golden.get("team") or ""))
    goals = int(golden.get("goals") or 0)
    return "\n".join([
        "📻 **R A D I O - P A S I L L O**",
        f"🏁 **FINALIZÓ LA TEMPORADA {int(season_number)}**",
        "",
        "🏆 **CAMPEÓN DE LIGA AJPA**",
        f"{final_base._club_emoji(guild, champion_team)} **{champion_team}**",
        f"🎩 **DT:** {final_base._mention(champion_dt)}",
        "",
        "👟 **GOLEADOR DE LA TEMPORADA**",
        f"⚽ **Jugador:** {player}",
        f"🥅 **Cant. goles:** {goals}",
        f"🏟️ **Equipo:** {final_base._club_emoji(guild, scorer_team)} {scorer_team}",
        f"🎩 **DT:** {final_base._mention(scorer_dt)}",
        "",
        "📊 **TABLA FINAL**",
        _compact_table(standings),
        "🎙️ *Radio Pasillo baja el telón de la temporada.*",
    ])


def _cup_text(guild, competition: str, season_number: int, champion: str, manager_id) -> str:
    is_champions = str(competition) == "champions"
    name = "CHAMPIONS AJPA" if is_champions else "EUROPA AJPA"
    icon = "🏆" if is_champions else "🟠"
    team = discord.utils.escape_markdown(str(champion or ""))
    return "\n".join([
        "📻 **R A D I O - P A S I L L O**",
        f"{icon} **FINALIZÓ LA {name}**",
        f"🗓️ **Temporada {int(season_number)}**",
        "",
        "👑 **CAMPEÓN**",
        f"{final_base._club_emoji(guild, team)} **{team}**",
        f"🎩 **DT:** {final_base._mention(manager_id)}",
        "",
        "🎙️ *Quedó escrito en la historia de AJPA.*",
    ])


async def _publish_seasons(runtime, bot, guild, channel) -> None:
    conn = league.db(runtime, int(guild.id))
    try:
        _ensure_schema(conn)
        conn.execute(f"UPDATE {_SEASON_EVENTS} SET guild_id=? WHERE guild_id=0", (int(guild.id),))
        conn.commit()
        rows = conn.execute(
            f"SELECT * FROM {_SEASON_EVENTS} WHERE guild_id=? AND status='pending' ORDER BY season_number,competition_id",
            (int(guild.id),),
        ).fetchall()
        jobs = [dict(row) for row in rows]
    finally:
        conn.close()

    for job in jobs:
        competition_id = int(job["competition_id"])
        season_number = int(job["season_number"])
        conn = league.db(runtime, int(guild.id))
        try:
            payload, cutoff = _snapshot(conn, competition_id)
            standings = list(payload.get("standings") or [])
            scorers = list(payload.get("scorers") or [])
            if not standings or not scorers:
                continue
            champion_team = str(standings[0].get("team") or "")
            scorer_team = str(scorers[0].get("team") or "")
            champion_dt = final_base._manager_as_of(conn, champion_team, cutoff)
            scorer_dt = final_base._manager_as_of(conn, scorer_team, cutoff)
        finally:
            conn.close()

        try:
            sent = await channel.send(
                content=_season_text(guild, season_number, standings, scorers, champion_dt, scorer_dt),
                allowed_mentions=discord.AllowedMentions(everyone=False, users=True, roles=False, replied_user=False),
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(f"AJAP Radio final temporada envío falló guild={guild.id} temporada={season_number}: {exc}")
            continue

        conn = league.db(runtime, int(guild.id))
        try:
            conn.execute(
                f"""UPDATE {_SEASON_EVENTS}
                    SET status='posted',channel_id=?,discord_message_id=?,posted_at=CURRENT_TIMESTAMP
                    WHERE competition_id=?""",
                (int(channel.id), int(sent.id), competition_id),
            )
            conn.commit()
        finally:
            conn.close()
        print(f"AJAP Radio Pasillo: cierre Temporada {season_number} publicado message={sent.id}")


async def _publish_cups(runtime, bot, guild, channel) -> None:
    conn = league.db(runtime, int(guild.id))
    try:
        if not _table_exists(conn, _CUP_EVENTS):
            return
        conn.execute(f"UPDATE {_CUP_EVENTS} SET guild_id=? WHERE guild_id=0", (int(guild.id),))
        conn.commit()
        rows = conn.execute(
            f"SELECT * FROM {_CUP_EVENTS} WHERE guild_id=? AND status='pending' ORDER BY edition_id,competition",
            (int(guild.id),),
        ).fetchall()
        jobs = [dict(row) for row in rows]
    finally:
        conn.close()

    for job in jobs:
        champion = str(job.get("champion") or "").strip()
        if not champion:
            continue
        conn = league.db(runtime, int(guild.id))
        try:
            manager_id = final_base._manager_as_of(conn, champion, None)
        finally:
            conn.close()
        try:
            sent = await channel.send(
                content=_cup_text(guild, str(job["competition"]), int(job["season_number"]), champion, manager_id),
                allowed_mentions=discord.AllowedMentions(everyone=False, users=True, roles=False, replied_user=False),
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(f"AJAP Radio final copa envío falló guild={guild.id} comp={job['competition']}: {exc}")
            continue

        conn = league.db(runtime, int(guild.id))
        try:
            conn.execute(
                f"""UPDATE {_CUP_EVENTS}
                    SET status='posted',channel_id=?,discord_message_id=?,posted_at=CURRENT_TIMESTAMP
                    WHERE edition_id=? AND competition=?""",
                (int(channel.id), int(sent.id), int(job["edition_id"]), str(job["competition"])),
            )
            conn.commit()
        finally:
            conn.close()
        print(f"AJAP Radio Pasillo: campeón {job['competition']} publicado message={sent.id}")


async def _publish_pending(runtime, bot, guild) -> None:
    channel = await radio._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        return
    await _publish_seasons(runtime, bot, guild, channel)
    await _publish_cups(runtime, bot, guild, channel)


async def _refresh_with_final_events(runtime, bot, guild_id: int):
    result = await _BASE_REFRESH(runtime, bot, int(guild_id))
    guild = bot.get_guild(int(guild_id)) if bot is not None else None
    if guild is not None:
        try:
            await _publish_pending(runtime, bot, guild)
        except Exception as exc:
            print(f"AJAP Radio final post-refresh guild={guild_id}: {type(exc).__name__}: {exc}")
    return result


league.refresh = _refresh_with_final_events


_BASE_APPLY = league.apply_league_automation_patch


def _apply_with_final_events(runtime, bot):
    _BASE_APPLY(runtime, bot)
    if getattr(runtime, "_ajpa_radio_final_events_ready", False):
        return

    async def watcher():
        while not bot.is_closed():
            for guild in list(getattr(bot, "guilds", []) or []):
                try:
                    await _publish_pending(runtime, bot, guild)
                except Exception as exc:
                    print(f"AJAP Radio final watcher guild={guild.id}: {type(exc).__name__}: {exc}")
            await asyncio.sleep(15)

    async def ready_listener():
        task = getattr(runtime, "_ajpa_radio_final_events_task", None)
        if task is None or task.done():
            runtime._ajpa_radio_final_events_task = asyncio.create_task(watcher())
        for guild in list(getattr(bot, "guilds", []) or []):
            try:
                await _publish_pending(runtime, bot, guild)
            except Exception as exc:
                print(f"AJAP Radio final on_ready guild={guild.id}: {type(exc).__name__}: {exc}")

    bot.add_listener(ready_listener, "on_ready")
    runtime._ajpa_radio_final_events_ready = True
    print("AJAP Radio Pasillo: cierres de Temporada + Champions + Europa automáticos activos")


league.apply_league_automation_patch = _apply_with_final_events
