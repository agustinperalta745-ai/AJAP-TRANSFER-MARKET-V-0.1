"""One-shot Radio Pasillo announcement for the AJPA preseason final.

On the next successful Discord ready event, publish one normal Radio Pasillo post
containing:
- preseason champion + the manager mention,
- a locally rendered full final standings image using AJPA's real club badges,
- Golden Boot winner + goals + club + the manager mention.

The post is persisted per guild/competition so reconnects or Railway restarts do
not duplicate it. It prefers the archived final snapshot, but can use the current
preseason snapshot for the explicit one-shot requested by Staff.
"""

from __future__ import annotations

import io
import json
import sqlite3
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


_BASE_APPLY = league.apply_league_automation_patch
_JOB_TABLE = "radio_pasillo_competition_final_posts"
_JOB_KIND = "preseason_final_radio_2026_09_10_v1"
_ACTIVE_ASSIGNMENT_ACTIONS = {"ASIGNADO", "ASIGNADO_VACANTE_ADMIN"}
_INACTIVE_ASSIGNMENT_ACTIONS = {"DESVINCULADO_ADMIN", "RENUNCIA_DT"}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _team_key(value: Any) -> str:
    raw = str(value or "").strip()
    try:
        canonical = league.canonical_team(raw)
        if canonical:
            raw = str(canonical)
    except Exception:
        pass
    return _norm(raw)


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _ensure_schema(conn) -> None:
    cycle.ensure_schema(conn)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_JOB_TABLE} (
            guild_id INTEGER NOT NULL,
            competition_id INTEGER NOT NULL,
            job_kind TEXT NOT NULL,
            channel_id INTEGER,
            discord_message_id INTEGER,
            posted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (guild_id, competition_id, job_kind)
        )
        """
    )
    conn.commit()


def _target_preseason(conn):
    _ensure_schema(conn)
    return conn.execute(
        """
        SELECT id, label, status, ended_at, final_snapshot_json
        FROM competition_editions
        WHERE kind='preseason'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def _snapshot_payload(conn, edition) -> dict[str, Any]:
    raw = str(edition["final_snapshot_json"] or "").strip()
    if not raw:
        raw = cycle._snapshot(conn, int(edition["id"]))
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    standings = list(payload.get("standings") or [])
    scorers = list(payload.get("scorers") or [])
    return {"standings": standings, "scorers": scorers}


def _already_posted(runtime, guild_id: int, competition_id: int) -> bool:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        return bool(
            conn.execute(
                f"""
                SELECT 1 FROM {_JOB_TABLE}
                WHERE guild_id=? AND competition_id=? AND job_kind=?
                LIMIT 1
                """,
                (int(guild_id), int(competition_id), _JOB_KIND),
            ).fetchone()
        )
    finally:
        conn.close()


def _mark_posted(
    runtime,
    guild_id: int,
    competition_id: int,
    channel_id: int,
    message_id: int,
) -> None:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_JOB_TABLE}
                (guild_id,competition_id,job_kind,channel_id,discord_message_id)
            VALUES (?,?,?,?,?)
            """,
            (
                int(guild_id),
                int(competition_id),
                _JOB_KIND,
                int(channel_id),
                int(message_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _manager_as_of(conn, team: str, cutoff: str | None) -> int | None:
    target = _team_key(team)
    if not target:
        return None

    if cutoff and _table_exists(conn, "club_assignment_history"):
        try:
            rows = conn.execute(
                """
                SELECT id,user_id,club,action,created_at
                FROM club_assignment_history
                WHERE created_at <= ?
                ORDER BY id DESC
                """,
                (str(cutoff),),
            ).fetchall()
            seen: set[int] = set()
            for row in rows:
                uid = int(row["user_id"])
                if uid in seen:
                    continue
                seen.add(uid)
                action = str(row["action"] or "").strip().upper()
                if action in _INACTIVE_ASSIGNMENT_ACTIONS:
                    continue
                if action not in _ACTIVE_ASSIGNMENT_ACTIONS:
                    continue
                if _team_key(row["club"]) == target:
                    return uid
        except sqlite3.Error:
            pass

    if _table_exists(conn, "clubs"):
        try:
            for row in conn.execute("SELECT user_id,name FROM clubs").fetchall():
                if _team_key(row["name"]) == target:
                    return int(row["user_id"])
        except sqlite3.Error:
            pass
    return None


def _mention(user_id: int | None) -> str:
    return f"<@{int(user_id)}>" if user_id else "DT no vinculado"


def _club_emoji(guild, team: str) -> str:
    try:
        return top5._club_emoji(guild, team)
    except Exception:
        return "⚽"


async def _badge_payloads(guild, rows: list[dict[str, Any]]) -> dict[str, bytes]:
    payloads: dict[str, bytes] = {}
    if badgefix is None:
        return payloads
    manual = getattr(badgefix, "_manual_emoji", None)
    if not callable(manual):
        return payloads
    for row in rows:
        team = str(row.get("team") or "")
        if not team:
            continue
        try:
            emoji = manual(guild, team)
            if emoji is None:
                continue
            data = await emoji.read()
            if data:
                payloads[_team_key(team)] = bytes(data)
        except Exception as exc:
            print(
                "WARNING AJAP Final Pretemporada: no se pudo leer escudo Discord "
                f"team={team!r}: {type(exc).__name__}: {exc}"
            )
    return payloads


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


def _row(row: dict[str, Any]) -> dict[str, Any]:
    gf = int(row.get("gf") or 0)
    gc = int(row.get("gc") or 0)
    dg = row.get("dg")
    if dg is None:
        dg = gf - gc
    return {
        "team": str(row.get("team") or "").strip(),
        "pj": int(row.get("pj") or 0),
        "pg": int(row.get("pg") or 0),
        "pe": int(row.get("pe") or 0),
        "pp": int(row.get("pp") or 0),
        "gf": gf,
        "gc": gc,
        "dg": int(dg or 0),
        "pts": int(row.get("pts") or row.get("points") or 0),
    }


async def _render_final_table(guild, raw_rows: list[dict[str, Any]]) -> io.BytesIO:
    rows = [_row(row) for row in raw_rows]
    payloads = await _badge_payloads(guild, rows)

    width = 1400
    row_h = 70
    top = 238
    footer_h = 95
    height = max(560, top + len(rows) * row_h + footer_h)

    image = Image.new("RGBA", (width, height), (13, 16, 24, 255))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (38, 34, width - 38, height - 34),
        radius=32,
        fill=(24, 29, 42, 255),
    )
    draw.rounded_rectangle(
        (38, 34, width - 38, 170),
        radius=32,
        fill=(35, 42, 59, 255),
    )
    draw.rectangle((38, 138, width - 38, 170), fill=(35, 42, 59, 255))

    title_font = top5._font(52, bold=True)
    sub_font = top5._font(25)
    header_font = top5._font(20, bold=True)
    team_font = top5._font(24, bold=True)
    stat_font = top5._font(22, bold=True)
    pos_font = top5._font(25, bold=True)

    draw.text((78, 62), "PRETEMPORADA", font=title_font, fill=(246, 248, 252, 255))
    draw.text(
        (78, 124),
        "TABLA FINAL • AJPA",
        font=sub_font,
        fill=(178, 187, 207, 255),
    )

    y_header = 192
    columns = [
        (76, "#"),
        (180, "EQUIPO"),
        (720, "PJ"),
        (795, "PG"),
        (870, "PE"),
        (945, "PP"),
        (1020, "GF"),
        (1095, "GC"),
        (1170, "DG"),
        (1270, "PTS"),
    ]
    for x, label in columns:
        draw.text((x, y_header), label, font=header_font, fill=(152, 162, 184, 255))

    for idx, row in enumerate(rows, start=1):
        y = top + (idx - 1) * row_h
        if idx == 1:
            fill = (64, 55, 30, 255)
        else:
            fill = (30, 36, 51, 255) if idx % 2 else (27, 33, 47, 255)
        draw.rounded_rectangle((62, y, width - 62, y + 56), radius=16, fill=fill)

        pos_text = f"{idx}"
        draw.text((84, y + 14), pos_text, font=pos_font, fill=(246, 248, 252, 255))

        badge = _badge_image(row["team"], payloads)
        if badge is not None and badge.getchannel("A").getbbox():
            badge.thumbnail((44, 44), Image.Resampling.LANCZOS)
            tile = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
            tile.alpha_composite(
                badge,
                ((50 - badge.width) // 2, (50 - badge.height) // 2),
            )
            image.alpha_composite(tile, (118, y + 3))

        name = top5._fit_text(draw, row["team"], team_font, 500)
        draw.text((180, y + 15), name, font=team_font, fill=(246, 248, 252, 255))

        values = [
            (724, row["pj"]),
            (799, row["pg"]),
            (874, row["pe"]),
            (949, row["pp"]),
            (1024, row["gf"]),
            (1099, row["gc"]),
        ]
        for x, value in values:
            draw.text((x, y + 16), str(int(value)), font=stat_font, fill=(225, 229, 238, 255))

        dg = int(row["dg"])
        dg_text = f"+{dg}" if dg > 0 else str(dg)
        draw.text((1168, y + 16), dg_text, font=stat_font, fill=(225, 229, 238, 255))
        draw.text(
            (1272, y + 13),
            str(int(row["pts"])),
            font=pos_font,
            fill=(255, 255, 255, 255),
        )

    draw.text(
        (78, height - 78),
        "AJPA • Radio Pasillo",
        font=top5._font(20, bold=True),
        fill=(143, 153, 174, 255),
    )

    out = io.BytesIO()
    image.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out


def _announcement_text(
    guild,
    champion: dict[str, Any],
    champion_dt: int | None,
    golden: dict[str, Any],
    golden_dt: int | None,
) -> str:
    champion_team = discord.utils.escape_markdown(str(champion.get("team") or ""))
    scorer = discord.utils.escape_markdown(str(golden.get("player") or ""))
    scorer_team = discord.utils.escape_markdown(str(golden.get("team") or ""))
    goals = int(golden.get("goals") or 0)
    noun = "gol" if goals == 1 else "goles"

    lines = [
        "📻 **R A D I O - P A S I L L O**",
        "🏁 **CIERRE DE PRETEMPORADA**",
        "",
        "🏆 **CAMPEÓN**",
        f"{_club_emoji(guild, champion_team)} **{champion_team}**",
        f"🎩 **DT:** {_mention(champion_dt)}",
        "",
        "📊 **TABLA FINAL**",
        "La clasificación definitiva está en la imagen adjunta, con todos los equipos y sus estadísticas.",
        "",
        "👟 **BOTA DE ORO**",
        f"⚽ **{scorer}** — **{goals} {noun}**",
        f"{_club_emoji(guild, scorer_team)} **{scorer_team}**",
        f"🎩 **DT:** {_mention(golden_dt)}",
        "",
        "🎙️ Se baja el telón de la pretemporada. Quedaron el campeón, la tabla definitiva y el goleador que mandó en las redes.",
    ]
    return "\n".join(lines)


async def _publish_for_guild(runtime, bot, guild) -> bool:
    conn = league.db(runtime, int(guild.id))
    try:
        edition = _target_preseason(conn)
        if edition is None:
            print(f"AJAP Final Pretemporada pendiente guild={guild.id}: no existe edición")
            return False

        competition_id = int(edition["id"])
        if _already_posted(runtime, guild.id, competition_id):
            return True

        payload = _snapshot_payload(conn, edition)
        standings = list(payload.get("standings") or [])
        scorers = list(payload.get("scorers") or [])
        if not standings or not scorers:
            print(
                f"AJAP Final Pretemporada pendiente guild={guild.id}: "
                f"standings={len(standings)} scorers={len(scorers)}"
            )
            return False

        champion = _row(dict(standings[0]))
        golden = dict(scorers[0])
        cutoff = str(edition["ended_at"] or "").strip() or None
        champion_dt = _manager_as_of(conn, champion["team"], cutoff)
        golden_dt = _manager_as_of(conn, str(golden.get("team") or ""), cutoff)
    finally:
        conn.close()

    channel = await top5._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(f"AJAP Final Pretemporada pendiente guild={guild.id}: Radio Pasillo no encontrado")
        return False

    try:
        image = await _render_final_table(guild, standings)
        sent = await channel.send(
            content=_announcement_text(
                guild,
                champion,
                champion_dt,
                golden,
                golden_dt,
            ),
            file=discord.File(
                image,
                filename=f"ajpa-pretemporada-tabla-final-{competition_id}.png",
            ),
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=True,
                roles=False,
                replied_user=False,
            ),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"AJAP Final Pretemporada envío falló guild={guild.id} "
            f"canal={getattr(channel, 'id', None)}: {exc}"
        )
        return False

    _mark_posted(runtime, guild.id, competition_id, channel.id, sent.id)
    print(
        f"AJAP Final Pretemporada publicado guild={guild.id} "
        f"competencia={competition_id} canal={channel.id} mensaje={sent.id}"
    )
    return True


def _apply_league_with_preseason_final(runtime, bot):
    _BASE_APPLY(runtime, bot)
    if getattr(runtime, "_ajap_preseason_final_radio_ready", False):
        return

    async def ready_listener():
        for guild in list(getattr(bot, "guilds", [])):
            try:
                await _publish_for_guild(runtime, bot, guild)
            except Exception as exc:
                print(
                    f"AJAP Final Pretemporada on_ready guild={guild.id}: "
                    f"{type(exc).__name__}: {exc}"
                )

    bot.add_listener(ready_listener, "on_ready")
    runtime._ajap_preseason_final_radio_ready = True
    print(
        "AJAP Radio Pasillo: anuncio final de Pretemporada activo "
        "(campeón + tabla completa + Bota de Oro + menciones de DT)"
    )


league.apply_league_automation_patch = _apply_league_with_preseason_final
