"""Radio Pasillo: automatic AJPA Season 1 final-stretch coverage.

The feature is evaluated after the authoritative Liga refresh triggered by
Staff's "GES actualizada" action. It never changes competitive data. When the
active competition is Temporada 1 and GES shows three or fewer pending
matchdays, Radio Pasillo publishes one preview per remaining matchday. A second,
one-shot definition alert is published when only two or three clubs remain
mathematically alive for the title.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import discord

import competition_cycle as cycle
import league_automation_patch as league
import league_ges_manual_sync_patch as ges
import league_top5_overtake_radio_patch as radio


_BASE_REFRESH = league.refresh
_EVENT_TABLE = "radio_pasillo_final_stretch_events"
SUPPORTED_SEASON_NUMBER = 1


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _ensure_schema(conn) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_EVENT_TABLE} (
            guild_id INTEGER NOT NULL,
            competition_id INTEGER NOT NULL,
            season_number INTEGER NOT NULL,
            event_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            channel_id INTEGER,
            discord_message_id INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            posted_at DATETIME,
            PRIMARY KEY (guild_id, competition_id, event_key)
        )
        """
    )
    conn.commit()


def _active_context(conn, guild_id: int) -> dict[str, Any] | None:
    cycle.ensure_schema(conn)
    state = conn.execute(
        "SELECT phase,season_number,competition_id FROM competition_cycle_state WHERE id=1"
    ).fetchone()
    if not state:
        return None
    if str(state["phase"] or "") != cycle.SEASON:
        return None
    season_number = int(state["season_number"] or 0)
    if season_number != SUPPORTED_SEASON_NUMBER or state["competition_id"] is None:
        return None
    competition_id = int(state["competition_id"])

    league_id = ""
    results_url = ""
    if _table_exists(conn, "league_ges_competition_config"):
        row = conn.execute(
            """SELECT league_id,results_url FROM league_ges_competition_config
               WHERE competition_id=? LIMIT 1""",
            (competition_id,),
        ).fetchone()
        if row:
            league_id = str(row["league_id"] or "").strip()
            results_url = str(row["results_url"] or "").strip()

    if not league_id and _table_exists(conn, "league_ges_sync_runs"):
        row = conn.execute(
            """SELECT league_id FROM league_ges_sync_runs
               WHERE guild_id=? ORDER BY id DESC LIMIT 1""",
            (int(guild_id),),
        ).fetchone()
        if row:
            league_id = str(row["league_id"] or "").strip()

    if not league_id or not _table_exists(conn, "league_ges_standings"):
        return None

    standings = [
        dict(row)
        for row in conn.execute(
            """SELECT position,team,pts,pj,pg,pe,pp,gf,gc,dg
               FROM league_ges_standings
               WHERE guild_id=? AND league_id=?
               ORDER BY position ASC, team COLLATE NOCASE ASC""",
            (int(guild_id), league_id),
        ).fetchall()
    ]
    if len(standings) < 2:
        return None

    scorers: list[dict[str, Any]] = []
    if _table_exists(conn, "league_ges_scorers"):
        scorers = [
            dict(row)
            for row in conn.execute(
                """SELECT player,team,goals FROM league_ges_scorers
                   WHERE guild_id=? AND league_id=?
                   ORDER BY goals DESC, player COLLATE NOCASE ASC LIMIT 3""",
                (int(guild_id), league_id),
            ).fetchall()
        ]

    return {
        "season_number": season_number,
        "competition_id": competition_id,
        "league_id": league_id,
        "results_url": results_url,
        "standings": standings,
        "scorers": scorers,
    }


def _parse_pending_fixtures(page: str) -> list[dict[str, Any]]:
    """Read GES result-grid cells such as ``J.17`` as pending fixtures."""
    pending: dict[tuple[str, str, int], dict[str, Any]] = {}
    matchday_re = re.compile(r"^\s*J\.?\s*(\d{1,3})\s*$", re.IGNORECASE)

    for table in ges._tables(page):
        for header_index, row in enumerate(table):
            headers: dict[int, str] = {}
            for index, cell in enumerate(row):
                try:
                    team = ges._canonical_team(cell)
                except Exception:
                    team = None
                if team:
                    headers[index] = str(team)
            if len(headers) < 3:
                continue

            for data_row in table[header_index + 1 :]:
                home = None
                for cell in data_row:
                    try:
                        candidate = ges._canonical_team(cell)
                    except Exception:
                        candidate = None
                    if candidate:
                        home = str(candidate)
                        break
                if not home:
                    continue

                for column, away in headers.items():
                    if column >= len(data_row) or away == home:
                        continue
                    marker = matchday_re.match(str(data_row[column] or ""))
                    if not marker:
                        continue
                    matchday = int(marker.group(1))
                    key = (home, away, matchday)
                    pending[key] = {
                        "home_team": home,
                        "away_team": away,
                        "matchday": matchday,
                    }
            break

    return sorted(
        pending.values(),
        key=lambda item: (
            int(item["matchday"]),
            str(item["home_team"]).casefold(),
            str(item["away_team"]).casefold(),
        ),
    )


def _remaining_games(standings: list[dict[str, Any]], fixtures: list[dict[str, Any]]) -> dict[str, int]:
    counts = {str(row["team"]): 0 for row in standings}
    if fixtures:
        for item in fixtures:
            home = str(item["home_team"])
            away = str(item["away_team"])
            if home in counts:
                counts[home] += 1
            if away in counts:
                counts[away] += 1
        return counts

    total_games = max(0, 2 * (len(standings) - 1))
    for row in standings:
        counts[str(row["team"])] = max(0, total_games - int(row.get("pj") or 0))
    return counts


def _remaining_matchdays(standings: list[dict[str, Any]], fixtures: list[dict[str, Any]]) -> int:
    if fixtures:
        return len({int(item["matchday"]) for item in fixtures})
    counts = _remaining_games(standings, fixtures)
    return max(counts.values(), default=0)


def _contenders(standings: list[dict[str, Any]], remaining: dict[str, int]) -> list[dict[str, Any]]:
    leader_points = max(int(row.get("pts") or 0) for row in standings)
    alive: list[dict[str, Any]] = []
    for row in standings:
        team = str(row["team"])
        games = int(remaining.get(team, 0))
        points = int(row.get("pts") or 0)
        maximum = points + (3 * games)
        if maximum >= leader_points:
            item = dict(row)
            item["remaining_games"] = games
            item["max_points"] = maximum
            alive.append(item)
    return alive


def _team_rank(standings: list[dict[str, Any]]) -> dict[str, int]:
    return {str(row["team"]): int(row.get("position") or index + 1) for index, row in enumerate(standings)}


def _key_fixture(fixtures: list[dict[str, Any]], standings: list[dict[str, Any]], contenders: list[dict[str, Any]]):
    if not fixtures:
        return None
    contender_names = {str(row["team"]) for row in contenders}
    ranks = _team_rank(standings)
    first_matchday = min(int(item["matchday"]) for item in fixtures)
    candidates = [item for item in fixtures if int(item["matchday"]) == first_matchday]

    def score(item):
        home, away = str(item["home_team"]), str(item["away_team"])
        both = int(home in contender_names) + int(away in contender_names)
        leader = int(ranks.get(home) == 1 or ranks.get(away) == 1)
        closeness = 50 - min(50, abs(ranks.get(home, 99) - ranks.get(away, 99)))
        return both * 1000 + leader * 200 + closeness

    return max(candidates, key=score) if candidates else None


def _elimination_fixture(
    fixtures: list[dict[str, Any]],
    standings: list[dict[str, Any]],
    contenders: list[dict[str, Any]],
    remaining: dict[str, int],
):
    if not fixtures or not contenders:
        return None
    leader_points = int(standings[0].get("pts") or 0)
    alive = {str(row["team"]): row for row in contenders}
    first_matchday = min(int(item["matchday"]) for item in fixtures)
    for item in fixtures:
        if int(item["matchday"]) != first_matchday:
            continue
        home, away = str(item["home_team"]), str(item["away_team"])
        for team in (home, away):
            row = alive.get(team)
            if not row or int(row.get("position") or 99) == 1:
                continue
            games = int(remaining.get(team, 0))
            max_after_loss = int(row.get("pts") or 0) + 3 * max(0, games - 1)
            if max_after_loss < leader_points:
                return item, team
    return None


def _recent_form(conn, competition_id: int, team: str, limit: int = 5) -> str:
    if not _table_exists(conn, "league_matches"):
        return "sin datos"
    rows = conn.execute(
        """SELECT home_team,away_team,home_goals,away_goals FROM league_matches
           WHERE competition_id=? AND (home_team=? OR away_team=?)
           ORDER BY id DESC LIMIT ?""",
        (int(competition_id), team, team, int(limit)),
    ).fetchall()
    marks: list[str] = []
    for row in reversed(rows):
        home = str(row["home_team"])
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        own, rival = (hg, ag) if home == team else (ag, hg)
        marks.append("G" if own > rival else "E" if own == rival else "P")
    return "-".join(marks) if marks else "sin datos"


def _dt_mention(guild) -> str:
    for role in list(getattr(guild, "roles", []) or []):
        if str(getattr(role, "name", "")).strip().casefold() == "dt":
            return role.mention
    return ""


def _preview_embed(
    context: dict[str, Any],
    remaining_matchdays: int,
    remaining: dict[str, int],
    contenders: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
    forms: dict[str, str],
) -> discord.Embed:
    season_number = int(context["season_number"])
    standings = list(context["standings"])
    leader = standings[0]
    embed = discord.Embed(
        title=f"🔥 LA RECTA FINAL — T{season_number}",
        description=(
            f"Quedan **{remaining_matchdays} fecha{'s' if remaining_matchdays != 1 else ''}** y la Temporada {season_number} "
            "entra en su tramo decisivo. Radio Pasillo hace las cuentas con la tabla oficial de GES."
        ),
        color=discord.Color.orange(),
    )

    candidate_lines = []
    leader_points = int(leader.get("pts") or 0)
    for row in contenders[:8]:
        team = str(row["team"])
        pts = int(row.get("pts") or 0)
        gap = max(0, leader_points - pts)
        suffix = "marca el ritmo y depende de sí mismo para sostener la punta" if int(row.get("position") or 0) == 1 else f"está a {gap} pt{'s' if gap != 1 else ''} de la punta"
        candidate_lines.append(
            f"**{int(row.get('position') or 0)}. {team}** — {pts} pts • "
            f"{int(remaining.get(team, 0))} PJ por jugar • máx. {int(row['max_points'])} • {suffix}."
        )
    embed.add_field(
        name="🏆 Candidatos al título",
        value="\n".join(candidate_lines) or "No hay candidatos calculables todavía.",
        inline=False,
    )

    key = _key_fixture(fixtures, standings, contenders)
    if key:
        embed.add_field(
            name="🔥 Partido clave de la próxima fecha",
            value=f"**J.{int(key['matchday'])} — {key['home_team']} vs {key['away_team']}**",
            inline=False,
        )

    danger = _elimination_fixture(fixtures, standings, contenders, remaining)
    if danger:
        item, team = danger
        embed.add_field(
            name="⚔️ Al borde",
            value=(
                f"**{team}** puede quedar matemáticamente afuera si pierde ante "
                f"**{item['away_team'] if item['home_team'] == team else item['home_team']}** en J.{int(item['matchday'])}."
            ),
            inline=False,
        )

    form_lines = [
        f"**{str(row['team'])}**: {forms.get(str(row['team']), 'sin datos')}"
        for row in contenders[:4]
    ]
    if form_lines:
        embed.add_field(name="📈 Cómo llegan", value="\n".join(form_lines), inline=False)

    scorers = list(context.get("scorers") or [])
    if scorers:
        scorer_lines = [
            f"**{index}. {row['player']}** — {row.get('team') or 'Sin club'} • ⚽ {int(row.get('goals') or 0)}"
            for index, row in enumerate(scorers[:3], 1)
        ]
        embed.add_field(name="🎯 Carrera por la Bota de Oro", value="\n".join(scorer_lines), inline=False)

    embed.set_footer(text="AJPA • Datos oficiales de GES • La Recta Final se actualiza con ‘GES actualizada’")
    return embed


def _definition_embed(context: dict[str, Any], contenders: list[dict[str, Any]]) -> discord.Embed:
    season_number = int(context["season_number"])
    names = " • ".join(str(row["team"]) for row in contenders)
    embed = discord.Embed(
        title="🚨 LA LIGA ENTRA EN ZONA DE DEFINICIÓN",
        description=(
            f"La **Temporada {season_number} de AJPA** quedó reducida matemáticamente a "
            f"**{len(contenders)} candidatos**.\n\n🏆 {names}\n\nDesde acá, cada punto puede decidir al campeón."
        ),
        color=discord.Color.gold(),
    )
    embed.set_footer(text="📻 Radio Pasillo • 🔥 La Recta Final")
    return embed


def _event_status(runtime, guild_id: int, competition_id: int, event_key: str):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        return conn.execute(
            f"""SELECT status FROM {_EVENT_TABLE}
                WHERE guild_id=? AND competition_id=? AND event_key=? LIMIT 1""",
            (int(guild_id), int(competition_id), str(event_key)),
        ).fetchone()
    finally:
        conn.close()


def _reserve_event(runtime, guild_id: int, competition_id: int, season_number: int, event_key: str) -> bool:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""INSERT OR IGNORE INTO {_EVENT_TABLE}
                (guild_id,competition_id,season_number,event_key,status)
                VALUES(?,?,?,?,'pending')""",
            (int(guild_id), int(competition_id), int(season_number), str(event_key)),
        )
        conn.commit()
        row = conn.execute(
            f"""SELECT status FROM {_EVENT_TABLE}
                WHERE guild_id=? AND competition_id=? AND event_key=? LIMIT 1""",
            (int(guild_id), int(competition_id), str(event_key)),
        ).fetchone()
        return bool(row and str(row["status"]) == "pending")
    finally:
        conn.close()


def _mark_posted(runtime, guild_id: int, competition_id: int, event_key: str, channel_id: int, message_id: int) -> None:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""UPDATE {_EVENT_TABLE}
                SET status='posted',channel_id=?,discord_message_id=?,posted_at=CURRENT_TIMESTAMP
                WHERE guild_id=? AND competition_id=? AND event_key=?""",
            (int(channel_id), int(message_id), int(guild_id), int(competition_id), str(event_key)),
        )
        conn.commit()
    finally:
        conn.close()


async def _publish_event(runtime, bot, guild, context: dict[str, Any], event_key: str, embed: discord.Embed) -> bool:
    existing = _event_status(runtime, guild.id, int(context["competition_id"]), event_key)
    if existing and str(existing["status"]) == "posted":
        return False
    if not _reserve_event(
        runtime,
        guild.id,
        int(context["competition_id"]),
        int(context["season_number"]),
        event_key,
    ):
        return False

    channel = await radio._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(f"AJPA Recta Final pendiente guild={guild.id}: Radio Pasillo no encontrado")
        return False

    mention = _dt_mention(guild)
    try:
        sent = await channel.send(
            content=mention or None,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=True,
                replied_user=False,
            ),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"AJPA Recta Final envío falló guild={guild.id} event={event_key}: {exc}")
        return False

    _mark_posted(
        runtime,
        guild.id,
        int(context["competition_id"]),
        event_key,
        int(channel.id),
        int(sent.id),
    )
    print(
        f"AJPA Radio Pasillo: Recta Final publicada guild={guild.id} "
        f"event={event_key} message={sent.id}"
    )
    return True


async def _evaluate(runtime, bot, guild) -> None:
    conn = league.db(runtime, int(guild.id))
    try:
        context = _active_context(conn, int(guild.id))
    finally:
        conn.close()
    if not context:
        return

    fixtures: list[dict[str, Any]] = []
    results_url = str(context.get("results_url") or "").strip()
    if results_url:
        try:
            page = await asyncio.to_thread(ges._fetch, results_url)
            fixtures = _parse_pending_fixtures(page)
        except Exception as exc:
            print(f"AJPA Recta Final: no se pudo releer fixture GES: {type(exc).__name__}: {exc}")

    standings = list(context["standings"])
    remaining = _remaining_games(standings, fixtures)
    remaining_matchdays = _remaining_matchdays(standings, fixtures)
    if remaining_matchdays <= 0 or remaining_matchdays > 3:
        return

    contenders = _contenders(standings, remaining)
    if not contenders:
        return

    conn = league.db(runtime, int(guild.id))
    try:
        forms = {
            str(row["team"]): _recent_form(
                conn,
                int(context["competition_id"]),
                str(row["team"]),
            )
            for row in contenders[:4]
        }
    finally:
        conn.close()

    await _publish_event(
        runtime,
        bot,
        guild,
        context,
        f"preview:{remaining_matchdays}",
        _preview_embed(context, remaining_matchdays, remaining, contenders, fixtures, forms),
    )

    if len(contenders) in {2, 3}:
        await _publish_event(
            runtime,
            bot,
            guild,
            context,
            "definition",
            _definition_embed(context, contenders),
        )


async def _refresh_with_final_stretch(runtime, bot, guild_id: int):
    result = await _BASE_REFRESH(runtime, bot, int(guild_id))
    guild = bot.get_guild(int(guild_id)) if bot is not None else None
    if guild is not None:
        try:
            await _evaluate(runtime, bot, guild)
        except Exception as exc:
            print(
                f"AJPA Recta Final post-refresh falló guild={guild_id}: "
                f"{type(exc).__name__}: {exc}"
            )
    return result


if not getattr(league.refresh, "_ajpa_final_stretch_wrapped", False):
    _refresh_with_final_stretch._ajpa_final_stretch_wrapped = True
    league.refresh = _refresh_with_final_stretch
    print("AJPA Radio Pasillo: 🔥 La Recta Final — T1 activa (trigger: GES actualizada)")
