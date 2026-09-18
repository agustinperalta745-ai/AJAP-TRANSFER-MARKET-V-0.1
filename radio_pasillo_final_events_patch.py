"""Automatic AJPA champion posters for official competition closes.

The official close paths are the only producers:
- competition_cycle.advance archives the Liga snapshot;
- mobile_cup_admin_reset_finalize_patch finalizes Champions/Europa.

No polling or resident watcher is used. Pending persisted events are recovered once
on Discord on_ready, covering a Railway restart between close and publication.
Pillow is imported only while an image is actually being generated.
"""

from __future__ import annotations

import asyncio
import gc
import io
import json
import os
from typing import Any

import discord

import competition_cycle as cycle
import league_automation_patch as league
import league_top5_overtake_radio_patch as radio
import mobile_cup_admin_reset_finalize_patch as cup_admin
import mobile_latest_honours_api_patch as honours


_SEASON_EVENTS = "radio_pasillo_official_season_final_events"
_CUP_EVENTS = "radio_pasillo_cup_final_events"

_RUNTIME = None
_BOT = None
_BOT_LOOP = None
_BASE_ADVANCE = None
_BASE_CUP_FINALIZE = None

_TROPHY_FILES = {
    "league": "mobile/assets/trophies/liga-ajpa.jpg",
    "champions": "mobile/assets/trophies/champions-ajpa.jpg",
    "europa": "mobile/assets/trophies/europa-ajpa.jpg",
}
_SUBTITLES = {
    "league": "CAMPEÓN DE LIGA",
    "champions": "CAMPEÓN DE CHAMPIONS LEAGUE",
    "europa": "CAMPEÓN DE EUROPA LEAGUE",
}
_COMPETITION_NAMES = {
    "league": "Liga AJPA",
    "champions": "Champions League",
    "europa": "Europa League",
}


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _columns(conn, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {
        str(row["name"])
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def _ensure_schema(conn) -> None:
    cycle.ensure_schema(conn)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_SEASON_EVENTS} (
            competition_id INTEGER PRIMARY KEY,
            season_number INTEGER NOT NULL,
            champion TEXT,
            manager_user_id INTEGER,
            manager_name TEXT,
            closed_at DATETIME,
            guild_id INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            channel_id INTEGER,
            discord_message_id INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            posted_at DATETIME
        )
        """
    )
    cols = _columns(conn, _SEASON_EVENTS)
    for name, definition in (
        ("champion", "TEXT"),
        ("manager_user_id", "INTEGER"),
        ("manager_name", "TEXT"),
        ("closed_at", "DATETIME"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE {_SEASON_EVENTS} ADD COLUMN {name} {definition}")
    cup_admin._ensure_schema(conn)
    conn.commit()


def _guild_id_hint(conn=None) -> int | None:
    """Resolve the guild from the actual SQLite file whenever possible."""
    if conn is not None and _RUNTIME is not None and _BOT is not None:
        try:
            db_row = conn.execute("PRAGMA database_list").fetchone()
            db_path = os.path.realpath(str(db_row["file"] or "")) if db_row else ""
            if db_path:
                for guild in list(getattr(_BOT, "guilds", []) or []):
                    candidate = os.path.realpath(str(_RUNTIME.guild_db_path(int(guild.id))))
                    if candidate == db_path:
                        return int(guild.id)
        except Exception:
            pass

    raw = (
        os.getenv("AJPA_MOBILE_GUILD_ID")
        or os.getenv("DISCORD_GUILD_ID")
        or ""
    ).strip()
    if raw.isdigit():
        return int(raw)

    if _RUNTIME is not None:
        try:
            value = int(_RUNTIME.current_guild_id())
            if value > 0:
                return value
        except Exception:
            pass
    return None


def _manager_snapshot(conn, team: str, closed_at: str | None) -> tuple[int | None, str]:
    data = honours.historical_manager_snapshot(conn, team, closed_at)
    raw_user_id = data.get("user_id")
    user_id = int(raw_user_id) if str(raw_user_id or "").isdigit() else None
    name = str(data.get("username") or "DT no registrado").strip() or "DT no registrado"
    return user_id, name


def _capture_season_event(
    conn,
    competition_id: int,
    season_number: int,
    guild_id: int | None,
) -> bool:
    row = conn.execute(
        """SELECT status,ended_at,final_snapshot_json
           FROM competition_editions WHERE id=? LIMIT 1""",
        (int(competition_id),),
    ).fetchone()
    if not row or str(row["status"] or "").casefold() != "finished":
        return False

    closed_at = str(row["ended_at"] or "").strip()
    raw = str(row["final_snapshot_json"] or "").strip()
    if not closed_at or not raw:
        return False

    try:
        payload = json.loads(raw)
    except Exception:
        return False
    standings = list(payload.get("standings") or []) if isinstance(payload, dict) else []
    if not standings:
        return False

    champion = str(standings[0].get("team") or "").strip()
    if not champion:
        return False

    manager_user_id, manager_name = _manager_snapshot(conn, champion, closed_at)
    conn.execute(
        f"""INSERT OR IGNORE INTO {_SEASON_EVENTS}
               (competition_id,season_number,champion,manager_user_id,manager_name,
                closed_at,guild_id,status,created_at)
           VALUES(?,?,?,?,?,?,?,'pending',CURRENT_TIMESTAMP)""",
        (
            int(competition_id),
            int(season_number),
            champion,
            manager_user_id,
            manager_name,
            closed_at,
            int(guild_id or 0),
        ),
    )
    conn.execute(
        f"""UPDATE {_SEASON_EVENTS}
            SET champion=COALESCE(NULLIF(champion,''),?),
                manager_user_id=COALESCE(manager_user_id,?),
                manager_name=CASE
                    WHEN manager_name IS NULL OR TRIM(manager_name)='' THEN ?
                    ELSE manager_name
                END,
                closed_at=COALESCE(closed_at,?),
                guild_id=CASE WHEN guild_id=0 AND ?>0 THEN ? ELSE guild_id END
            WHERE competition_id=?""",
        (
            champion,
            manager_user_id,
            manager_name,
            closed_at,
            int(guild_id or 0),
            int(guild_id or 0),
            int(competition_id),
        ),
    )
    conn.commit()
    return True


def _wrap_official_closes() -> None:
    global _BASE_ADVANCE, _BASE_CUP_FINALIZE

    if not getattr(cycle.advance, "_ajpa_champion_radio_close", False):
        _BASE_ADVANCE = cycle.advance

        def advance_with_champion_event(conn, user_id, expected_phase=None):
            cycle.ensure_schema(conn)
            before = conn.execute(
                "SELECT phase,season_number,competition_id "
                "FROM competition_cycle_state WHERE id=1"
            ).fetchone()
            old_phase = str(before["phase"] or "") if before else ""
            old_season = int(before["season_number"] or 1) if before else 1
            old_cid = (
                int(before["competition_id"])
                if before and before["competition_id"] is not None
                else None
            )
            guild_id = _guild_id_hint(conn)

            result = _BASE_ADVANCE(conn, user_id, expected_phase)

            if old_phase == cycle.SEASON and old_cid is not None:
                try:
                    _ensure_schema(conn)
                    if _capture_season_event(conn, old_cid, old_season, guild_id):
                        _schedule_publish(guild_id, delay=0.0)
                except Exception as exc:
                    print(
                        "AJPA champion Radio: cierre de Liga no encolado "
                        f"competition={old_cid}: {type(exc).__name__}: {exc}"
                    )
            return result

        advance_with_champion_event._ajpa_champion_radio_close = True
        cycle.advance = advance_with_champion_event

    if not getattr(cup_admin.finalize_competition, "_ajpa_champion_radio_close", False):
        _BASE_CUP_FINALIZE = cup_admin.finalize_competition

        def finalize_with_champion_event(conn, edition_id: int, competition: str):
            result = _BASE_CUP_FINALIZE(conn, int(edition_id), str(competition))
            if result.get("ok"):
                # The mobile HTTP wrapper commits immediately after this returns.
                # One delayed task avoids racing that commit; it is not polling.
                _schedule_publish(_guild_id_hint(conn), delay=0.35)
            return result

        finalize_with_champion_event._ajpa_champion_radio_close = True
        cup_admin.finalize_competition = finalize_with_champion_event


def _load_badge(team_name: str):
    from PIL import Image

    try:
        import league_top5_badge_fix_patch as badgefix

        func = getattr(badgefix, "_badge_image", None)
        if callable(func):
            badge = func(team_name, None)
            if badge is not None:
                return badge.convert("RGBA")
    except Exception:
        pass

    path = radio._asset_path(team_name)
    if not path or not os.path.isfile(path):
        return None
    try:
        with Image.open(path) as source:
            badge = source.convert("RGBA")
            bbox = badge.getchannel("A").getbbox()
            return badge.crop(bbox) if bbox else badge
    except Exception:
        return None


def _fit_font(draw, text: str, max_width: int, start: int, minimum: int, bold: bool = True):
    size = int(start)
    while size > minimum:
        font = radio._font(size, bold=bold)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
        size -= 2
    return radio._font(minimum, bold=bold)


def _center_text(draw, canvas_width: int, y: int, text: str, font, fill) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    draw.text(((canvas_width - width) / 2, y), text, font=font, fill=fill)


def build_champion_poster(
    competition_type,
    team_name,
    manager_name,
    season_number,
):
    """Return the official Radio Pasillo champion poster as an in-memory PNG."""
    key = str(competition_type or "").strip().lower()
    if key not in _TROPHY_FILES:
        raise ValueError(f"Competencia de campeón inválida: {competition_type!r}")

    # Pillow stays outside module startup and is loaded only for this one render.
    from PIL import Image, ImageDraw, ImageFilter, ImageOps

    trophy_path = os.path.join(os.path.dirname(__file__), _TROPHY_FILES[key])
    if not os.path.isfile(trophy_path):
        raise FileNotFoundError(
            f"Falta el asset oficial de copa para {key}: {_TROPHY_FILES[key]}"
        )

    width, height = 1200, 1500

    gradient = Image.linear_gradient("L").resize((width, height))
    image = ImageOps.colorize(
        gradient,
        black=(7, 11, 20),
        white=(18, 35, 40),
    ).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")

    # Stadium bowl, pitch and floodlights.
    draw.ellipse((-260, 190, width + 260, 1130), fill=(19, 30, 48, 225))
    draw.ellipse((-130, 340, width + 130, 1160), fill=(8, 13, 23, 245))
    draw.polygon(
        [(110, 1070), (1090, 1070), (1200, 1490), (0, 1490)],
        fill=(18, 57, 47, 210),
    )
    for line_y in (1120, 1210, 1300):
        draw.line((115, line_y, 1085, line_y), fill=(160, 205, 190, 48), width=3)

    for x in (90, 1110):
        draw.rectangle((x - 12, 190, x + 12, 540), fill=(82, 91, 111, 180))
        for row in range(5):
            for col in range(3):
                cx = x - 36 + col * 36
                cy = 170 + row * 25
                draw.ellipse(
                    (cx - 9, cy - 9, cx + 9, cy + 9),
                    fill=(255, 246, 201, 235),
                )

    # Stadium haze and smoke.
    smoke = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    smoke_draw = ImageDraw.Draw(smoke, "RGBA")
    for i in range(12):
        cx = 70 + (i * 103) % 1120
        cy = 560 + (i * 71) % 500
        rw = 160 + (i * 29) % 170
        rh = 80 + (i * 19) % 120
        smoke_draw.ellipse(
            (cx - rw, cy - rh, cx + rw, cy + rh),
            fill=(215, 222, 235, 24 + (i % 4) * 8),
        )
    smoke = smoke.filter(ImageFilter.GaussianBlur(34))
    image = Image.alpha_composite(image, smoke)
    draw = ImageDraw.Draw(image, "RGBA")

    # Real AJPA club badge enlarged behind the trophy.
    badge = _load_badge(str(team_name))
    if badge is not None:
        badge.thumbnail((680, 680), Image.Resampling.LANCZOS)
        alpha = badge.getchannel("A").point(lambda a: int(a * 0.27))
        badge.putalpha(alpha)
        image.alpha_composite(
            badge,
            ((width - badge.width) // 2, 410),
        )

    # Competition-specific AJPA trophy asset, never a generic fallback.
    with Image.open(trophy_path) as source:
        trophy = source.convert("RGB")
    trophy = ImageOps.contain(
        trophy,
        (540, 560),
        method=Image.Resampling.LANCZOS,
    )
    frame = Image.new("RGBA", (590, 610), (0, 0, 0, 0))
    frame_draw = ImageDraw.Draw(frame, "RGBA")
    frame_draw.rounded_rectangle(
        (8, 8, 582, 602),
        radius=38,
        fill=(5, 8, 14, 208),
        outline=(228, 234, 245, 52),
        width=2,
    )
    frame.alpha_composite(
        trophy.convert("RGBA"),
        ((frame.width - trophy.width) // 2, (frame.height - trophy.height) // 2),
    )
    image.alpha_composite(frame, ((width - frame.width) // 2, 470))

    # Pedestal and deterministic confetti.
    draw = ImageDraw.Draw(image, "RGBA")
    draw.polygon(
        [(360, 1060), (840, 1060), (920, 1210), (280, 1210)],
        fill=(19, 22, 31, 245),
        outline=(221, 227, 238, 95),
    )
    draw.rounded_rectangle(
        (240, 1200, 960, 1325),
        radius=24,
        fill=(11, 14, 21, 250),
        outline=(231, 236, 245, 85),
        width=2,
    )

    accents = [
        (241, 197, 70, 220),
        (228, 235, 248, 210),
        (69, 123, 181, 210),
    ]
    for i in range(54):
        x = 25 + (i * 197) % 1140
        y = 350 + (i * 113) % 870
        w = 5 + (i % 4) * 2
        h = 12 + (i % 5) * 3
        draw.rounded_rectangle(
            (x, y, x + w, y + h),
            radius=2,
            fill=accents[i % len(accents)],
        )

    club = str(team_name or "").strip().upper()
    subtitle = _SUBTITLES[key]
    manager = str(manager_name or "DT no registrado").strip() or "DT no registrado"
    season = f"TEMPORADA {int(season_number)}"

    club_font = _fit_font(draw, club, 1040, 76, 42, True)
    subtitle_font = _fit_font(draw, subtitle, 1030, 42, 30, True)
    season_font = radio._font(25, bold=True)
    bottom = f"{str(team_name).strip()} - {manager}"
    line_font = _fit_font(draw, bottom, 1040, 34, 24, True)

    _center_text(draw, width, 85, club, club_font, (248, 249, 252, 255))
    _center_text(draw, width, 178, subtitle, subtitle_font, (239, 202, 91, 255))
    _center_text(draw, width, 242, season, season_font, (181, 190, 210, 255))
    _center_text(draw, width, 1240, bottom, line_font, (245, 247, 251, 255))
    footer_font = radio._font(20, bold=True)
    _center_text(
        draw,
        width,
        1410,
        "AJPA • R A D I O - P A S I L L O",
        footer_font,
        (151, 162, 183, 255),
    )

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)

    # Release every large Pillow object before returning the compact buffer.
    for obj in (badge, trophy, frame, smoke, image, gradient):
        if obj is not None:
            try:
                obj.close()
            except Exception:
                pass
    gc.collect()
    return output


async def _existing_message_id(channel, filename: str) -> int | None:
    """Recover send-before-marker crashes using the deterministic attachment name."""
    try:
        async for message in channel.history(limit=100):
            bot_user = getattr(_BOT, "user", None)
            if bot_user is not None and getattr(message.author, "id", None) != bot_user.id:
                continue
            for attachment in list(getattr(message, "attachments", []) or []):
                if str(getattr(attachment, "filename", "")) == filename:
                    return int(message.id)
    except (discord.Forbidden, discord.HTTPException):
        return None
    return None


def _mark_season_posted(
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
            f"""UPDATE {_SEASON_EVENTS}
                SET status='posted',guild_id=?,channel_id=?,discord_message_id=?,
                    posted_at=COALESCE(posted_at,CURRENT_TIMESTAMP)
                WHERE competition_id=?""",
            (int(guild_id), int(channel_id), int(message_id), int(competition_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _mark_cup_posted(
    runtime,
    guild_id: int,
    edition_id: int,
    competition: str,
    channel_id: int,
    message_id: int,
) -> None:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""UPDATE {_CUP_EVENTS}
                SET status='posted',guild_id=?,channel_id=?,discord_message_id=?,
                    posted_at=COALESCE(posted_at,CURRENT_TIMESTAMP)
                WHERE edition_id=? AND competition=?""",
            (
                int(guild_id),
                int(channel_id),
                int(message_id),
                int(edition_id),
                str(competition),
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def _send_poster_once(
    channel,
    filename: str,
    content: str,
    competition: str,
    team: str,
    manager_name: str,
    season_number: int,
) -> int | None:
    existing = await _existing_message_id(channel, filename)
    if existing is not None:
        return existing

    payload = None
    try:
        payload = build_champion_poster(
            competition,
            team,
            manager_name,
            season_number,
        )
        sent = await channel.send(
            content=content,
            file=discord.File(payload, filename=filename),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return int(sent.id)
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"AJPA champion Radio envío falló competition={competition} "
            f"team={team!r}: {exc}"
        )
        return None
    except Exception as exc:
        print(
            f"AJPA champion Radio poster falló competition={competition} "
            f"team={team!r}: {type(exc).__name__}: {exc}"
        )
        return None
    finally:
        if payload is not None:
            try:
                payload.close()
            except Exception:
                pass
        gc.collect()


def _validate_season_job(conn, job: dict[str, Any]) -> tuple[str, str, int] | None:
    row = conn.execute(
        """SELECT status,ended_at,final_snapshot_json,season_number
           FROM competition_editions WHERE id=? LIMIT 1""",
        (int(job["competition_id"]),),
    ).fetchone()
    if not row or str(row["status"] or "").casefold() != "finished":
        return None

    closed_at = str(row["ended_at"] or "").strip()
    raw = str(row["final_snapshot_json"] or "").strip()
    if not closed_at or not raw:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    standings = list(payload.get("standings") or []) if isinstance(payload, dict) else []
    if not standings:
        return None

    champion = str(standings[0].get("team") or "").strip()
    if not champion:
        return None

    manager_user_id, manager_name = _manager_snapshot(conn, champion, closed_at)
    conn.execute(
        f"""UPDATE {_SEASON_EVENTS}
            SET champion=?, closed_at=?,
                manager_user_id=COALESCE(manager_user_id,?),
                manager_name=CASE
                    WHEN manager_name IS NULL OR TRIM(manager_name)='' THEN ?
                    ELSE manager_name
                END
            WHERE competition_id=?""",
        (
            champion,
            closed_at,
            manager_user_id,
            manager_name,
            int(job["competition_id"]),
        ),
    )
    conn.commit()

    stored_name = str(job.get("manager_name") or manager_name).strip()
    if not stored_name:
        stored_name = "DT no registrado"
    return champion, stored_name, int(row["season_number"] or job["season_number"])


def _validate_cup_job(conn, job: dict[str, Any]) -> tuple[str, str, int] | None:
    competition = str(job["competition"])
    if competition not in {"champions", "europa"}:
        return None

    finished_field = (
        "champions_finished_at" if competition == "champions" else "europa_finished_at"
    )
    champion_field = (
        "champions_champion" if competition == "champions" else "europa_champion"
    )
    cols = _columns(conn, "cup_tournament_editions")
    if finished_field not in cols or champion_field not in cols:
        return None

    row = conn.execute(
        f"""SELECT season_number,{champion_field} AS champion,
                   {finished_field} AS closed_at
            FROM cup_tournament_editions WHERE id=? LIMIT 1""",
        (int(job["edition_id"]),),
    ).fetchone()
    if not row:
        return None

    closed_at = str(row["closed_at"] or "").strip()
    champion = str(row["champion"] or "").strip()
    if not closed_at or not champion:
        return None

    manager_user_id, manager_name = _manager_snapshot(conn, champion, closed_at)
    conn.execute(
        f"""UPDATE {_CUP_EVENTS}
            SET champion=?, closed_at=COALESCE(closed_at,?),
                manager_user_id=COALESCE(manager_user_id,?),
                manager_name=CASE
                    WHEN manager_name IS NULL OR TRIM(manager_name)='' THEN ?
                    ELSE manager_name
                END
            WHERE edition_id=? AND competition=?""",
        (
            champion,
            closed_at,
            manager_user_id,
            manager_name,
            int(job["edition_id"]),
            competition,
        ),
    )
    conn.commit()

    stored_name = str(job.get("manager_name") or manager_name).strip()
    if not stored_name:
        stored_name = "DT no registrado"
    return champion, stored_name, int(row["season_number"] or job["season_number"])


async def _publish_seasons(runtime, bot, guild, channel) -> None:
    conn = league.db(runtime, int(guild.id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"UPDATE {_SEASON_EVENTS} SET guild_id=? WHERE guild_id=0",
            (int(guild.id),),
        )
        conn.commit()
        jobs = [
            dict(row)
            for row in conn.execute(
                f"""SELECT * FROM {_SEASON_EVENTS}
                    WHERE guild_id=? AND status='pending'
                    ORDER BY season_number,competition_id""",
                (int(guild.id),),
            ).fetchall()
        ]
    finally:
        conn.close()

    for job in jobs:
        conn = league.db(runtime, int(guild.id))
        try:
            valid = _validate_season_job(conn, job)
        finally:
            conn.close()
        if valid is None:
            continue

        champion, manager_name, season_number = valid
        competition_id = int(job["competition_id"])
        filename = (
            f"ajpa-champion-league-s{season_number}-competition-{competition_id}.png"
        )
        message_id = await _send_poster_once(
            channel,
            filename,
            f"🏆 **{discord.utils.escape_markdown(champion)}** es el nuevo campeón de **Liga AJPA**.",
            "league",
            champion,
            manager_name,
            season_number,
        )
        if message_id is not None:
            _mark_season_posted(
                runtime,
                guild.id,
                competition_id,
                channel.id,
                message_id,
            )


async def _publish_cups(runtime, bot, guild, channel) -> None:
    conn = league.db(runtime, int(guild.id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"UPDATE {_CUP_EVENTS} SET guild_id=? WHERE guild_id=0",
            (int(guild.id),),
        )
        conn.commit()
        jobs = [
            dict(row)
            for row in conn.execute(
                f"""SELECT * FROM {_CUP_EVENTS}
                    WHERE guild_id=? AND status='pending'
                    ORDER BY edition_id,competition""",
                (int(guild.id),),
            ).fetchall()
        ]
    finally:
        conn.close()

    for job in jobs:
        conn = league.db(runtime, int(guild.id))
        try:
            valid = _validate_cup_job(conn, job)
        finally:
            conn.close()
        if valid is None:
            continue

        champion, manager_name, season_number = valid
        competition = str(job["competition"])
        edition_id = int(job["edition_id"])
        filename = (
            f"ajpa-champion-{competition}-s{season_number}-edition-{edition_id}.png"
        )
        message_id = await _send_poster_once(
            channel,
            filename,
            f"🏆 **{discord.utils.escape_markdown(champion)}** es el nuevo campeón de **{_COMPETITION_NAMES[competition]}**.",
            competition,
            champion,
            manager_name,
            season_number,
        )
        if message_id is not None:
            _mark_cup_posted(
                runtime,
                guild.id,
                edition_id,
                competition,
                channel.id,
                message_id,
            )


async def _publish_pending(runtime, bot, guild) -> None:
    channel = await radio._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        return
    await _publish_seasons(runtime, bot, guild, channel)
    await _publish_cups(runtime, bot, guild, channel)


async def _publish_after_delay(guild, delay: float) -> None:
    if delay > 0:
        await asyncio.sleep(delay)
    try:
        await _publish_pending(_RUNTIME, _BOT, guild)
    except Exception as exc:
        print(
            f"AJPA champion Radio publicación puntual guild={guild.id}: "
            f"{type(exc).__name__}: {exc}"
        )


def _schedule_publish(guild_id: int | None, delay: float = 0.0) -> None:
    if _BOT is None or _BOT_LOOP is None or not _BOT_LOOP.is_running():
        return

    target = int(guild_id) if guild_id else None

    def kickoff():
        guild = _BOT.get_guild(target) if target else None
        if guild is None:
            guilds = list(getattr(_BOT, "guilds", []) or [])
            if len(guilds) == 1:
                guild = guilds[0]
        if guild is not None:
            _BOT_LOOP.create_task(_publish_after_delay(guild, float(delay)))

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is _BOT_LOOP:
        kickoff()
    else:
        _BOT_LOOP.call_soon_threadsafe(kickoff)


def apply_radio_pasillo_final_events_patch(runtime, bot) -> None:
    global _RUNTIME, _BOT, _BOT_LOOP
    _RUNTIME, _BOT = runtime, bot
    if getattr(runtime, "_ajpa_champion_radio_final_events_ready", False):
        return

    _wrap_official_closes()

    async def ready_listener():
        global _BOT_LOOP
        _BOT_LOOP = asyncio.get_running_loop()
        for guild in list(getattr(bot, "guilds", []) or []):
            try:
                await _publish_pending(runtime, bot, guild)
            except Exception as exc:
                print(
                    f"AJPA champion Radio recuperación guild={guild.id}: "
                    f"{type(exc).__name__}: {exc}"
                )

    bot.add_listener(ready_listener, "on_ready")
    runtime.build_champion_poster = build_champion_poster
    runtime._ajpa_champion_radio_final_events_ready = True
    print(
        "AJPA Radio Pasillo: campeones Liga + Champions + Europa activos "
        "(cierre oficial, poster local, DT histórico, sin polling)"
    )
