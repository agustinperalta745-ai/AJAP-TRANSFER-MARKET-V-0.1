"""Radio Pasillo: columna deportiva automática basada únicamente en datos reales de AJPA.

Se integra con la misma rotación de Radio Pasillo: no crea un loop adicional ni
aumenta la frecuencia de publicaciones. Las notas se construyen desde la
competencia activa, resultados, tabla, goleadores y planteles de clubes que
tienen un DT enlazado.
"""

from __future__ import annotations

import math
import random
import time
from contextlib import closing

import discord

import competition_cycle
import league_automation_patch as league
import radio_pasillo_feature_ads_patch as radio


SPORTS_COLUMN_CHANCE = 0.40
SPORTS_KEY_PREFIX = "journal|"


def _norm(value) -> str:
    try:
        return league.norm(value)
    except Exception:
        return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _canonical_team(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return raw
    try:
        return str(league.canonical_team(raw) or raw)
    except Exception:
        return raw


def _team_key(value) -> str:
    return _norm(_canonical_team(value))


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _linked_clubs(conn):
    if not _table_exists(conn, "clubs"):
        return []
    try:
        rows = conn.execute(
            """
            SELECT name
            FROM clubs
            WHERE user_id IS NOT NULL
              AND TRIM(COALESCE(name, '')) <> ''
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
    except Exception:
        return []
    return [str(row["name"]).strip() for row in rows if row["name"]]


def _competition_label(conn, competition_id: int) -> str:
    if _table_exists(conn, "competition_editions"):
        row = conn.execute(
            "SELECT label FROM competition_editions WHERE id=? LIMIT 1",
            (int(competition_id),),
        ).fetchone()
        if row and row["label"]:
            return str(row["label"]).strip()
    return "la competencia actual"


def _resolve_team(raw: str, known_names) -> str:
    raw = str(raw or "").strip()
    if not raw:
        return raw

    known = {_team_key(name): str(name) for name in known_names if str(name or "").strip()}
    hit = known.get(_team_key(raw))
    if hit:
        return hit

    try:
        canonical = league.canonical_team(raw)
    except Exception:
        canonical = None
    if canonical:
        return known.get(_team_key(canonical), str(canonical))

    return raw


def _all_current_matches(conn, competition_id: int):
    if not _table_exists(conn, "league_matches"):
        return []
    try:
        return conn.execute(
            """
            SELECT id, home_team, away_team, home_goals, away_goals, created_at
            FROM league_matches
            WHERE competition_id=?
            ORDER BY id ASC
            """,
            (int(competition_id),),
        ).fetchall()
    except Exception:
        return []


def _build_standings(matches, linked_clubs):
    names = []
    for name in getattr(league, "TEAMS", []):
        if str(name or "").strip():
            names.append(str(name))
    names.extend(str(name) for name in linked_clubs if str(name or "").strip())
    for row in matches:
        names.extend((str(row["home_team"]), str(row["away_team"])))

    unique = {}
    for name in names:
        unique.setdefault(_team_key(name), _canonical_team(name))

    table = {
        key: {
            "team": name,
            "pj": 0,
            "pg": 0,
            "pe": 0,
            "pp": 0,
            "gf": 0,
            "gc": 0,
            "pts": 0,
        }
        for key, name in unique.items()
        if key
    }

    for row in matches:
        hk, ak = _team_key(row["home_team"]), _team_key(row["away_team"])
        if not hk or not ak:
            continue
        table.setdefault(
            hk,
            {"team": _canonical_team(row["home_team"]), "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0},
        )
        table.setdefault(
            ak,
            {"team": _canonical_team(row["away_team"]), "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0},
        )
        h, a = table[hk], table[ak]
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        h["pj"] += 1
        a["pj"] += 1
        h["gf"] += hg
        h["gc"] += ag
        a["gf"] += ag
        a["gc"] += hg
        if hg > ag:
            h["pg"] += 1
            a["pp"] += 1
            h["pts"] += 3
        elif ag > hg:
            a["pg"] += 1
            h["pp"] += 1
            a["pts"] += 3
        else:
            h["pe"] += 1
            a["pe"] += 1
            h["pts"] += 1
            a["pts"] += 1

    rows = list(table.values())
    for item in rows:
        item["dg"] = item["gf"] - item["gc"]
    rows.sort(
        key=lambda item: (
            -item["pts"],
            -item["dg"],
            -item["gf"],
            -item["pg"],
            _norm(item["team"]),
        )
    )
    total = len(rows)
    for index, item in enumerate(rows, 1):
        item["pos"] = index
        item["total"] = total
    return rows


def _team_matches(matches, team: str):
    key = _team_key(team)
    output = []
    for row in reversed(matches):
        home = _team_key(row["home_team"]) == key
        away = _team_key(row["away_team"]) == key
        if not home and not away:
            continue
        tg = int(row["home_goals"] if home else row["away_goals"])
        og = int(row["away_goals"] if home else row["home_goals"])
        opponent = _canonical_team(row["away_team"] if home else row["home_team"])
        result = "W" if tg > og else "L" if tg < og else "D"
        output.append(
            {
                "id": int(row["id"]),
                "team_goals": tg,
                "opp_goals": og,
                "opponent": opponent,
                "result": result,
            }
        )
    return output


def _streak(recent, accepted):
    count = 0
    for item in recent:
        if item["result"] in accepted:
            count += 1
        else:
            break
    return count


def _points_in(items):
    return sum(3 if item["result"] == "W" else 1 if item["result"] == "D" else 0 for item in items)


def _team_scorers(conn, competition_id: int, team: str):
    if not _table_exists(conn, "league_goal_events"):
        return []
    try:
        rows = conn.execute(
            """
            SELECT player, team, SUM(goals) AS goals
            FROM league_goal_events
            WHERE competition_id=?
            GROUP BY player COLLATE NOCASE, COALESCE(team, '') COLLATE NOCASE
            ORDER BY goals DESC, player COLLATE NOCASE ASC
            """,
            (int(competition_id),),
        ).fetchall()
    except Exception:
        return []

    target = _team_key(team)
    output = []
    for row in rows:
        if _team_key(row["team"]) != target:
            continue
        goals = int(row["goals"] or 0)
        if goals <= 0:
            continue
        output.append({"player": str(row["player"]), "goals": goals})
    return output


def _team_roster(conn, team: str):
    if not _table_exists(conn, "roster_players"):
        return []
    try:
        rows = conn.execute("SELECT name, club FROM roster_players").fetchall()
    except Exception:
        return []
    target = _team_key(team)
    return [
        str(row["name"])
        for row in rows
        if row["name"] and _team_key(row["club"]) == target
    ]


def _player_line(team: str, scorers, roster, *, positive: bool):
    if scorers:
        pool = scorers[: min(3, len(scorers))]
        scorer = random.choice(pool)
        goals = int(scorer["goals"])
        player = scorer["player"]
        if positive:
            return (
                f"🎯 **{player}** acompaña el momento con **{goals} "
                f"{'gol' if goals == 1 else 'goles'} registrado{'s' if goals != 1 else ''}."
            )
        return (
            f"🎯 Dentro de ese panorama, **{player}** suma **{goals} "
            f"{'gol' if goals == 1 else 'goles'} registrado{'s' if goals != 1 else ''} para {team}."
        )

    if roster:
        player = random.choice(roster)
        if positive:
            return f"👤 **{player}** es uno de los futbolistas que integran el plantel que hoy ocupa esa zona de la tabla."
        return f"👤 Entre los nombres del plantel aparece **{player}**; el equipo necesita mejorar sus números para escalar posiciones."
    return ""


def _story_key(competition_id: int, team: str, topic: str, latest_match_id: int) -> str:
    return f"{SPORTS_KEY_PREFIX}{int(competition_id)}|{_team_key(team)}|{topic}|{int(latest_match_id)}"


def _stories_for_team(conn, competition_id: int, label: str, row, recent):
    if not recent:
        return []

    team = str(row["team"])
    latest = recent[0]
    scorers = _team_scorers(conn, competition_id, team)
    roster = _team_roster(conn, team)
    positive_line = _player_line(team, scorers, roster, positive=True)
    pressure_line = _player_line(team, scorers, roster, positive=False)
    suffix_pos = f" Hoy está **{row['pos']}.º** con **{row['pts']} puntos**."
    stories = []

    if latest["result"] == "W":
        body = (
            f"🔥 **{team} salió fortalecido**\n"
            f"**{team}** venció **{latest['team_goals']}-{latest['opp_goals']}** a "
            f"**{latest['opponent']}** en {label}.{suffix_pos}"
        )
        if positive_line:
            body += f"\n{positive_line}"
        stories.append((_story_key(competition_id, team, "last_win", latest["id"]), body))

    elif latest["result"] == "D":
        body = (
            f"📰 **{team} dejó puntos en el camino**\n"
            f"**{team} no logró vencer a {latest['opponent']}**: igualó "
            f"**{latest['team_goals']}-{latest['opp_goals']}** en {label}.{suffix_pos}"
        )
        if scorers:
            body += f"\n{_player_line(team, scorers, roster, positive=True)}"
        stories.append((_story_key(competition_id, team, "last_draw", latest["id"]), body))

    else:
        body = (
            f"📉 **{team} tropezó ante {latest['opponent']}**\n"
            f"El último registro de {label} dejó una derrota **{latest['team_goals']}-{latest['opp_goals']}** "
            f"para **{team}** frente a **{latest['opponent']}**.{suffix_pos}"
        )
        if pressure_line:
            body += f"\n{pressure_line}"
        stories.append((_story_key(competition_id, team, "last_loss", latest["id"]), body))

    pj = int(row["pj"])
    total = int(row["total"])
    if pj >= 2 and total:
        zone_size = max(2, int(math.ceil(total * 0.25)))
        is_top = int(row["pos"]) <= zone_size
        is_bottom = int(row["pos"]) > max(0, total - zone_size)
        last_three = recent[:3]
        recent_pts = _points_in(last_three)

        if is_top:
            body = (
                f"📈 **{team} se mueve en la zona alta**\n"
                f"Los números de {label} ubican a **{team} {row['pos']}.º de {total}**, "
                f"con **{row['pts']} puntos en {pj} partidos**. "
                f"En sus últimos {len(last_three)} encuentros sumó **{recent_pts} puntos**."
            )
            if positive_line:
                body += f"\n{positive_line}"
            stories.append((_story_key(competition_id, team, "top_zone", latest["id"]), body))

        if is_bottom:
            winless = _streak(recent, {"D", "L"})
            if winless >= 3:
                body = (
                    f"⚠️ **{team} necesita reaccionar**\n"
                    f"**{team}** ocupa el **{row['pos']}.º puesto de {total}** con **{row['pts']} puntos** "
                    f"y acumula **{winless} partidos sin ganar** en {label}."
                )
            else:
                body = (
                    f"📉 **{team}, obligado a mirar hacia arriba**\n"
                    f"**{team}** aparece **{row['pos']}.º de {total}** con **{row['pts']} puntos** "
                    f"tras {pj} partidos de {label}. En sus últimos {len(last_three)} encuentros "
                    f"sumó **{recent_pts} puntos**."
                )
            if pressure_line:
                body += f"\n{pressure_line}"
            stories.append((_story_key(competition_id, team, "bottom_zone", latest["id"]), body))

    unbeaten = _streak(recent, {"W", "D"})
    wins = _streak(recent, {"W"})
    winless = _streak(recent, {"D", "L"})

    if unbeaten >= 3:
        body = (
            f"🛡️ **{team} sostiene una racha positiva**\n"
            f"**{team} lleva {unbeaten} partidos sin perder** en {label} y se mantiene "
            f"en el **{row['pos']}.º puesto** con **{row['pts']} puntos**."
        )
        if positive_line:
            body += f"\n{positive_line}"
        stories.append((_story_key(competition_id, team, "unbeaten", latest["id"]), body))

    if wins >= 2:
        body = (
            f"🔥 **{team} encadenó victorias**\n"
            f"El equipo suma **{wins} triunfos consecutivos** en {label}. "
            f"La racha lo encuentra **{row['pos']}.º** con **{row['pts']} puntos**."
        )
        if positive_line:
            body += f"\n{positive_line}"
        stories.append((_story_key(competition_id, team, "winning_streak", latest["id"]), body))

    if winless >= 3:
        body = (
            f"🧊 **{team} atraviesa un tramo sin victorias**\n"
            f"Los resultados muestran **{winless} partidos consecutivos sin ganar** para **{team}** "
            f"en {label}. El club está **{row['pos']}.º** con **{row['pts']} puntos**."
        )
        if pressure_line:
            body += f"\n{pressure_line}"
        stories.append((_story_key(competition_id, team, "winless", latest["id"]), body))

    if scorers:
        scorer = scorers[0]
        goals = int(scorer["goals"])
        body = (
            f"🎯 **{scorer['player']}, nombre propio en {team}**\n"
            f"**{scorer['player']}** lleva **{goals} {'gol' if goals == 1 else 'goles'} registrados** "
            f"para **{team}** en {label}. El equipo marcha **{row['pos']}.º** "
            f"con **{row['pts']} puntos**."
        )
        stories.append((_story_key(competition_id, team, "scorer", latest["id"]), body))

    return stories


def _sports_candidates(guild_id: int, last_key: str | None):
    with closing(radio._conn_for_guild(guild_id)) as conn:
        try:
            competition_id = competition_cycle.active_competition_id(conn)
            conn.commit()
        except Exception:
            return []
        if competition_id is None:
            return []

        linked = _linked_clubs(conn)
        if not linked:
            return []

        matches = _all_current_matches(conn, competition_id)
        if not matches:
            return []

        label = _competition_label(conn, competition_id)
        standings = _build_standings(matches, linked)
        by_norm = {_team_key(row["team"]): row for row in standings}

        known_names = [row["team"] for row in standings]
        all_stories = []

        for linked_name in linked:
            team = _resolve_team(linked_name, known_names)
            row = by_norm.get(_team_key(team))
            if not row or int(row["pj"]) <= 0:
                continue
            recent = _team_matches(matches, row["team"])
            stories = _stories_for_team(conn, competition_id, label, row, recent)
            if stories:
                all_stories.extend(stories)

    if not all_stories:
        return []

    # No repetir exactamente la misma nota si los datos no cambiaron.
    filtered = [story for story in all_stories if story[0] != last_key]
    if filtered:
        all_stories = filtered

    # Si la nota anterior también fue periodística, priorizar otro club cuando
    # haya más de uno con contenido elegible.
    if last_key and str(last_key).startswith(SPORTS_KEY_PREFIX):
        parts = str(last_key).split("|")
        previous_team = parts[2] if len(parts) > 2 else ""
        other_clubs = [
            story
            for story in all_stories
            if len(story[0].split("|")) > 2 and story[0].split("|")[2] != previous_team
        ]
        if other_clubs:
            all_stories = other_clubs

    return all_stories


def _select_message(guild_id: int, last_key: str | None):
    static_message = radio._next_ad(last_key)
    sports = _sports_candidates(guild_id, last_key)

    if sports and (static_message is None or random.random() < SPORTS_COLUMN_CHANCE):
        return random.choice(sports)

    return static_message or (random.choice(sports) if sports else None)


async def _send_due_with_sports(guild) -> bool:
    if guild is None:
        return False

    now = int(time.time())
    with closing(radio._conn_for_guild(guild.id)) as conn:
        row = radio._state(conn, guild.id)
        last_sent_at = int(row["last_sent_at"]) if row else 0
        last_key = str(row["last_ad_key"]) if row and row["last_ad_key"] else None

    if last_sent_at and now - last_sent_at < radio.INTERVAL_SECONDS:
        return False

    channel = await radio._resolve_radio_channel(guild)
    if channel is None:
        print(f"AJAP Radio Pasillo: canal no encontrado guild={guild.id}")
        return False

    role = radio._dt_role(guild)
    if role is None:
        print(f"AJAP Radio Pasillo: rol DT no encontrado guild={guild.id}")
        return False

    selected = _select_message(guild.id, last_key)
    if selected is None:
        return False
    message_key, body = selected

    is_sports = str(message_key).startswith(SPORTS_KEY_PREFIX)
    header = (
        "🗞️ **RADIO PASILLO • COLUMNA DEPORTIVA**"
        if is_sports
        else "📻 **RADIO PASILLO • RECORDATORIO AJPA**"
    )
    content = f"{role.mention}\n{header}\n{body}"

    try:
        sent = await channel.send(
            content=content,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=True,
                replied_user=False,
            ),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            "AJAP Radio Pasillo: envío falló "
            f"guild={guild.id} channel={getattr(channel, 'id', None)} "
            f"error={type(exc).__name__}: {exc}"
        )
        return False

    with closing(radio._conn_for_guild(guild.id)) as conn:
        radio._mark_sent(
            conn,
            guild.id,
            now=now,
            ad_key=message_key,
            channel_id=channel.id,
            message_id=sent.id,
        )

    print(
        "AJAP Radio Pasillo enviada "
        f"guild={guild.id} channel={channel.id} "
        f"type={'sports' if is_sports else 'reminder'} key={message_key}"
    )
    return True


# La tarea existente hace lookup global de radio._send_due en cada ciclo. Al
# reemplazar esa referencia, conservamos exactamente el mismo timer de 2 horas.
radio._send_due = _send_due_with_sports
print("AJAP Radio Pasillo: columna deportiva basada en datos reales activa")
