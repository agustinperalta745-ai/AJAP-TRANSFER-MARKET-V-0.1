"""Radio Pasillo: Top 5 de goleadores, con el mismo formato del Top 5 de Liga.

- Publica una foto real del Top 5 actual una sola vez al desplegar esta versión.
- Después solo vuelve a publicar cuando un goleador que YA estaba entre los cinco
  primeros sube de posición superando en goles a otro que también estaba arriba.
- Lee exclusivamente la competencia activa (Pretemporada/Temporada/Copa).
- Usa los mismos emojis/escudos de club que el Top 5 de Liga.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import unicodedata
from typing import Any

import discord
from PIL import Image, ImageDraw

import competition_cycle as cycle
import league_automation_patch as league
import league_top5_overtake_radio_patch as top5

try:
    import league_top5_badge_fix_patch as badgefix
except Exception:
    badgefix = None


_BASE_REFRESH = league.refresh
_SNAPSHOT_TABLE = "league_top5_scorer_snapshot"
_EVENT_TABLE = "league_top5_scorer_radio_events"
_ONE_TIME_TABLE = "ajap_one_time_jobs"
_LIVE_KEY = "radio_top5_scorers_live_2026_09_04_v1"
_LOCKS: dict[int, asyncio.Lock] = {}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _player_key(row: dict[str, Any]) -> str:
    return f"{_norm(row.get('player'))}|{_norm(row.get('team'))}"


def _ensure_schema(conn) -> None:
    cycle.ensure_schema(conn)
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {_SNAPSHOT_TABLE} (
            guild_id INTEGER PRIMARY KEY,
            competition_id INTEGER,
            payload_json TEXT NOT NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS {_EVENT_TABLE} (
            event_key TEXT PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            competition_id INTEGER,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            moves_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            channel_id INTEGER,
            discord_message_id INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            posted_at DATETIME
        );

        CREATE TABLE IF NOT EXISTS {_ONE_TIME_TABLE} (
            guild_id INTEGER NOT NULL,
            job_key TEXT NOT NULL,
            completed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            discord_message_id INTEGER,
            PRIMARY KEY (guild_id, job_key)
        );
        """
    )
    conn.commit()


def _top5_scorers(runtime, guild_id: int) -> tuple[int | None, list[dict[str, Any]]]:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        cid = cycle.active_competition_id(conn)
        if cid is None:
            return None, []
        rows = conn.execute(
            """
            SELECT player, COALESCE(team, '') AS team, SUM(goals) AS goals
            FROM league_goal_events
            WHERE competition_id=?
            GROUP BY player COLLATE NOCASE, COALESCE(team, '') COLLATE NOCASE
            HAVING SUM(goals) > 0
            ORDER BY goals DESC, player COLLATE NOCASE ASC
            LIMIT 5
            """,
            (int(cid),),
        ).fetchall()
        return int(cid), [
            {
                "player": str(row["player"] or "").strip(),
                "team": str(row["team"] or "").strip(),
                "goals": int(row["goals"] or 0),
            }
            for row in rows
        ]
    finally:
        conn.close()


def _load_snapshot(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        return conn.execute(
            f"SELECT competition_id,payload_json FROM {_SNAPSHOT_TABLE} WHERE guild_id=? LIMIT 1",
            (int(guild_id),),
        ).fetchone()
    finally:
        conn.close()


def _save_snapshot(
    runtime,
    guild_id: int,
    competition_id: int | None,
    rows: list[dict[str, Any]],
) -> None:
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""
            INSERT INTO {_SNAPSHOT_TABLE}(guild_id,competition_id,payload_json,updated_at)
            VALUES(?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                competition_id=excluded.competition_id,
                payload_json=excluded.payload_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (int(guild_id), competition_id, payload),
        )
        conn.commit()
    finally:
        conn.close()


def _detect_overtakes(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    before_pos = {_player_key(row): idx + 1 for idx, row in enumerate(before[:5])}
    after_pos = {_player_key(row): idx + 1 for idx, row in enumerate(after[:5])}
    before_by_key = {_player_key(row): row for row in before[:5]}
    after_by_key = {_player_key(row): row for row in after[:5]}
    moves: list[dict[str, Any]] = []

    # Misma regla que el Top 5 de clubes: solo importa quien ya estaba 1.º-5.º.
    for key, current in after_by_key.items():
        old_pos = before_pos.get(key)
        new_pos = after_pos.get(key)
        old = before_by_key.get(key)
        if old_pos is None or new_pos is None or old is None or new_pos >= old_pos:
            continue

        # Evita movimientos por desempate alfabético o por una corrección ajena:
        # el goleador que sube tiene que haber aumentado su propio total.
        if int(current["goals"]) <= int(old["goals"]):
            continue

        passed: list[dict[str, Any]] = []
        for other_key, other_old_pos in before_pos.items():
            if other_key == key or other_old_pos >= old_pos:
                continue
            other_new_pos = after_pos.get(other_key)
            other_after = after_by_key.get(other_key)
            if other_new_pos is None or other_after is None or other_new_pos <= new_pos:
                continue
            # Empatar no es superar: tiene que quedar con más goles.
            if int(current["goals"]) <= int(other_after["goals"]):
                continue
            passed.append(
                {
                    "player": str(other_after["player"]),
                    "team": str(other_after["team"]),
                    "old_pos": int(other_old_pos),
                    "new_pos": int(other_new_pos),
                    "goals": int(other_after["goals"]),
                }
            )

        if passed:
            passed.sort(key=lambda item: item["old_pos"])
            moves.append(
                {
                    "player": str(current["player"]),
                    "team": str(current["team"]),
                    "old_pos": int(old_pos),
                    "new_pos": int(new_pos),
                    "goals_before": int(old["goals"]),
                    "goals_after": int(current["goals"]),
                    "passed": passed,
                }
            )

    moves.sort(key=lambda item: (item["new_pos"], item["old_pos"], _norm(item["player"])))
    return moves


def _event_key(
    guild_id: int,
    competition_id: int | None,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> str:
    raw = json.dumps(
        {
            "guild": int(guild_id),
            "competition": competition_id,
            "before": before,
            "after": after,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _store_event(
    runtime,
    guild_id: int,
    competition_id: int | None,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    moves: list[dict[str, Any]],
) -> str:
    key = _event_key(guild_id, competition_id, before, after)
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_EVENT_TABLE}
                (event_key,guild_id,competition_id,before_json,after_json,moves_json,status)
            VALUES (?,?,?,?,?,?,'pending')
            """,
            (
                key,
                int(guild_id),
                competition_id,
                json.dumps(before, ensure_ascii=False, separators=(",", ":")),
                json.dumps(after, ensure_ascii=False, separators=(",", ":")),
                json.dumps(moves, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return key


def _event(runtime, guild_id: int, event_key: str):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        return conn.execute(
            f"SELECT * FROM {_EVENT_TABLE} WHERE event_key=? LIMIT 1",
            (str(event_key),),
        ).fetchone()
    finally:
        conn.close()


def _mark_event_posted(
    runtime,
    guild_id: int,
    event_key: str,
    channel_id: int,
    message_id: int,
) -> None:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""
            UPDATE {_EVENT_TABLE}
            SET status='posted',channel_id=?,discord_message_id=?,posted_at=CURRENT_TIMESTAMP
            WHERE event_key=?
            """,
            (int(channel_id), int(message_id), str(event_key)),
        )
        conn.commit()
    finally:
        conn.close()


def _dt_mention(guild) -> str:
    for role in list(getattr(guild, "roles", []) or []):
        if str(getattr(role, "name", "")).strip().casefold() == "dt":
            return str(getattr(role, "mention", "@DT"))
    return "@DT"


def _club_emoji(guild, team: str) -> str:
    if not team:
        return "⚽"
    return top5._club_emoji(guild, team)


def _snapshot_text(guild, rows: list[dict[str, Any]]) -> str:
    lines = [
        _dt_mention(guild),
        "",
        "📻 **R A D I O - P A S I L L O**",
        "🥅 **TOP 5 DE GOLEADORES**",
        "",
    ]
    for pos, row in enumerate(rows[:5], start=1):
        goals = int(row["goals"])
        noun = "gol" if goals == 1 else "goles"
        player = discord.utils.escape_markdown(str(row["player"]))
        lines.append(
            f"**{pos}.** {_club_emoji(guild, str(row['team']))} **{player}** • {goals} {noun}"
        )
    return "\n".join(lines)


async def _badge_payloads(guild, rows) -> dict[str, bytes]:
    if badgefix is not None:
        func = getattr(badgefix, "_discord_badge_payloads", None)
        if callable(func):
            try:
                return await func(guild, rows)
            except Exception as exc:
                print(f"WARNING AJAP Goleadores Top5: precarga de escudos falló: {exc}")
    return {}


def _badge_image(team: str, payloads: dict[str, bytes]):
    if badgefix is not None:
        func = getattr(badgefix, "_badge_image", None)
        if callable(func):
            try:
                return func(team, payloads)
            except Exception:
                pass

    path = top5._asset_path(team)
    if not path:
        return None
    try:
        with Image.open(path) as source:
            badge = source.convert("RGBA")
            bbox = badge.getchannel("A").getbbox()
            return badge.crop(bbox) if bbox else badge
    except Exception:
        return None


async def _render_top5_scorers(guild, rows: list[dict[str, Any]]) -> io.BytesIO:
    payloads = await _badge_payloads(guild, rows)
    width, height = 1200, 860
    image = Image.new("RGBA", (width, height), (13, 16, 24, 255))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (42, 38, width - 42, height - 38),
        radius=34,
        fill=(24, 29, 42, 255),
    )
    draw.rounded_rectangle(
        (42, 38, width - 42, 172),
        radius=34,
        fill=(35, 42, 59, 255),
    )
    draw.rectangle((42, 138, width - 42, 172), fill=(35, 42, 59, 255))

    title_font = top5._font(52, bold=True)
    sub_font = top5._font(25)
    header_font = top5._font(23, bold=True)
    player_font = top5._font(29, bold=True)
    club_font = top5._font(25, bold=True)
    goals_font = top5._font(34, bold=True)
    pos_font = top5._font(34, bold=True)

    draw.text((82, 66), "GOLEADORES", font=title_font, fill=(246, 248, 252, 255))
    draw.text(
        (82, 126),
        "TOP 5 • TABLA ACTUALIZADA",
        font=sub_font,
        fill=(178, 187, 207, 255),
    )

    y_header = 194
    draw.text((84, y_header), "#", font=header_font, fill=(152, 162, 184, 255))
    draw.text((170, y_header), "JUGADOR", font=header_font, fill=(152, 162, 184, 255))
    draw.text((650, y_header), "CLUB", font=header_font, fill=(152, 162, 184, 255))
    draw.text((1090, y_header), "G", font=header_font, fill=(152, 162, 184, 255))

    row_top = 238
    row_h = 112
    for idx, row in enumerate(rows[:5], start=1):
        y = row_top + (idx - 1) * row_h
        fill = (30, 36, 51, 255) if idx % 2 else (27, 33, 47, 255)
        draw.rounded_rectangle((68, y, width - 68, y + 94), radius=22, fill=fill)

        pos = str(idx)
        pos_box = draw.textbbox((0, 0), pos, font=pos_font)
        pos_w = pos_box[2] - pos_box[0]
        draw.text(
            (112 - pos_w / 2, y + 25),
            pos,
            font=pos_font,
            fill=(244, 246, 250, 255),
        )

        player = top5._fit_text(draw, str(row["player"]), player_font, 420)
        draw.text((170, y + 29), player, font=player_font, fill=(246, 248, 252, 255))

        team = str(row["team"] or "")
        badge = _badge_image(team, payloads) if team else None
        if badge is not None and badge.getchannel("A").getbbox():
            badge.thumbnail((62, 62), Image.Resampling.LANCZOS)
            tile = Image.new("RGBA", (68, 68), (0, 0, 0, 0))
            tile.alpha_composite(
                badge,
                ((68 - badge.width) // 2, (68 - badge.height) // 2),
            )
            image.alpha_composite(tile, (620, y + 13))

        club = top5._fit_text(draw, team or "—", club_font, 335)
        draw.text((695, y + 31), club, font=club_font, fill=(225, 229, 238, 255))
        draw.text(
            (1082, y + 25),
            str(int(row["goals"])),
            font=goals_font,
            fill=(255, 255, 255, 255),
        )

    draw.text(
        (82, height - 82),
        "AJPA • Radio Pasillo",
        font=top5._font(21, bold=True),
        fill=(143, 153, 174, 255),
    )

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


async def _publish_event(runtime, bot, guild, event_key: str) -> bool:
    row = _event(runtime, guild.id, event_key)
    if not row:
        return False
    if str(row["status"] or "").casefold() == "posted":
        return True

    channel = await top5._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(f"AJAP Goleadores Top5 pendiente guild={guild.id}: Radio Pasillo no encontrado")
        return False

    try:
        after = json.loads(str(row["after_json"]))
    except Exception as exc:
        print(f"AJAP Goleadores Top5 evento inválido key={event_key[:10]}: {exc}")
        return False

    try:
        image = await _render_top5_scorers(guild, after)
        sent = await channel.send(
            content=_snapshot_text(guild, after),
            file=discord.File(image, filename=f"ajpa-top5-goleadores-{event_key[:12]}.png"),
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=True,
            ),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"AJAP Goleadores Top5 envío falló guild={guild.id} "
            f"canal={getattr(channel, 'id', None)}: {exc}"
        )
        return False

    _mark_event_posted(runtime, guild.id, event_key, channel.id, sent.id)
    print(
        f"AJAP Goleadores Top5 publicado guild={guild.id} "
        f"canal={channel.id} mensaje={sent.id}"
    )
    return True


async def _publish_pending(runtime, bot, guild) -> None:
    conn = league.db(runtime, int(guild.id))
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            f"""
            SELECT event_key FROM {_EVENT_TABLE}
            WHERE guild_id=? AND status='pending'
            ORDER BY created_at
            LIMIT 50
            """,
            (int(guild.id),),
        ).fetchall()
        keys = [str(row["event_key"]) for row in rows]
    finally:
        conn.close()

    for key in keys:
        try:
            await _publish_event(runtime, bot, guild, key)
        except Exception as exc:
            print(f"AJAP Goleadores Top5 retry falló guild={guild.id}: {exc}")


async def _observe(runtime, bot, guild_id: int) -> None:
    cid, current = _top5_scorers(runtime, int(guild_id))
    previous = _load_snapshot(runtime, int(guild_id))

    if previous is None:
        _save_snapshot(runtime, int(guild_id), cid, current)
        return

    old_cid = (
        int(previous["competition_id"])
        if previous["competition_id"] is not None
        else None
    )
    try:
        before = json.loads(str(previous["payload_json"]))
    except Exception:
        before = []

    # Una competencia nueva arranca de cero: nunca compara contra la anterior.
    if old_cid != cid:
        _save_snapshot(runtime, int(guild_id), cid, current)
        return

    if before == current:
        return

    moves = _detect_overtakes(before, current)
    event_key = None
    if moves:
        event_key = _store_event(
            runtime,
            int(guild_id),
            cid,
            before,
            current,
            moves,
        )

    # La foto lógica se avanza aunque no haya adelantamiento. Así el próximo
    # cambio se compara contra el estado real inmediatamente anterior.
    _save_snapshot(runtime, int(guild_id), cid, current)

    if event_key:
        guild = bot.get_guild(int(guild_id)) if bot is not None else None
        if guild is not None:
            await _publish_event(runtime, bot, guild, event_key)


async def _refresh_with_scorer_radio(runtime, bot, guild_id: int):
    result = await _BASE_REFRESH(runtime, bot, int(guild_id))
    lock = _LOCKS.setdefault(int(guild_id), asyncio.Lock())
    async with lock:
        try:
            await _observe(runtime, bot, int(guild_id))
        except Exception as exc:
            # Radio Pasillo no puede romper la tabla oficial de Liga.
            print(f"AJAP Goleadores Top5 observación falló guild={guild_id}: {exc}")
    return result


league.refresh = _refresh_with_scorer_radio


def _already_sent_live(runtime, guild_id: int) -> bool:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        return bool(
            conn.execute(
                f"SELECT 1 FROM {_ONE_TIME_TABLE} WHERE guild_id=? AND job_key=? LIMIT 1",
                (int(guild_id), _LIVE_KEY),
            ).fetchone()
        )
    finally:
        conn.close()


def _mark_live_sent(runtime, guild_id: int, message_id: int) -> None:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_ONE_TIME_TABLE}(guild_id,job_key,discord_message_id)
            VALUES (?,?,?)
            """,
            (int(guild_id), _LIVE_KEY, int(message_id)),
        )
        conn.commit()
    finally:
        conn.close()


async def _publish_live_snapshot(runtime, bot, guild) -> bool:
    if guild is None or _already_sent_live(runtime, guild.id):
        return True

    cid, rows = _top5_scorers(runtime, guild.id)
    if not rows:
        print(f"AJAP Goleadores Top5 real pendiente guild={guild.id}: tabla vacía")
        return False

    channel = await top5._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(f"AJAP Goleadores Top5 real pendiente guild={guild.id}: Radio Pasillo no encontrado")
        return False

    try:
        image = await _render_top5_scorers(guild, rows)
        sent = await channel.send(
            content=_snapshot_text(guild, rows),
            file=discord.File(image, filename="ajpa-top5-goleadores-radio-pasillo.png"),
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=True,
            ),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"AJAP Goleadores Top5 real envío falló guild={guild.id} "
            f"canal={getattr(channel, 'id', None)}: {exc}"
        )
        return False

    _mark_live_sent(runtime, guild.id, sent.id)
    _save_snapshot(runtime, guild.id, cid, rows)
    print(
        f"AJAP Goleadores Top5 real publicado guild={guild.id} "
        f"canal={channel.id} mensaje={sent.id}"
    )
    return True


# Bot.run vuelve a consultar league.apply_league_automation_patch justo antes de
# conectar Discord, así que este wrapper agrega el on_ready aunque Liga ya se haya
# instalado durante el arranque normal de run_bot.
_BASE_APPLY = league.apply_league_automation_patch


def _apply_league_with_scorer_radio(runtime, bot):
    _BASE_APPLY(runtime, bot)
    if getattr(runtime, "_ajap_top5_scorers_radio_ready", False):
        return

    async def ready_listener():
        for guild in list(getattr(bot, "guilds", [])):
            try:
                await _publish_pending(runtime, bot, guild)
                await _publish_live_snapshot(runtime, bot, guild)
            except Exception as exc:
                print(f"AJAP Goleadores Top5 on_ready guild={guild.id}: {exc}")

    bot.add_listener(ready_listener, "on_ready")
    runtime._ajap_top5_scorers_radio_ready = True
    print(
        "AJAP Radio Pasillo: Top 5 de goleadores activo "
        "(foto real + adelantamientos 1.º-5.º)"
    )


league.apply_league_automation_patch = _apply_league_with_scorer_radio
