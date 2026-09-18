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

_POSTER_VERSION = 2


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
            poster_version INTEGER NOT NULL DEFAULT 1,
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
        ("poster_version", "INTEGER NOT NULL DEFAULT 1"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE {_SEASON_EVENTS} ADD COLUMN {name} {definition}")

    cup_admin._ensure_schema(conn)
    cup_cols = _columns(conn, _CUP_EVENTS)
    if "poster_version" not in cup_cols:
        conn.execute(
            f"ALTER TABLE {_CUP_EVENTS} "
            "ADD COLUMN poster_version INTEGER NOT NULL DEFAULT 1"
        )
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
    """Render the fixed AJPA champion-poster composition approved with Fulham.

    The visual hierarchy intentionally mirrors that reference:
    giant club crest behind the cup, trophy in the foreground, black pedestal,
    stadium/crowd atmosphere, smoke/confetti, huge club name, champion subtitle,
    and the final Club - DT line. Only the dynamic competition data changes.
    """
    key = str(competition_type or "").strip().lower()
    if key not in _TROPHY_FILES:
        raise ValueError(f"Competencia de campeón inválida: {competition_type!r}")

    # Railway Free: Pillow remains completely lazy and is imported for this
    # one render only. No OpenCV/OCR/AI dependency is introduced.
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

    root = os.path.dirname(__file__)
    trophy_path = os.path.join(root, _TROPHY_FILES[key])
    if not os.path.isfile(trophy_path):
        raise FileNotFoundError(
            f"Falta el asset oficial de copa para {key}: {_TROPHY_FILES[key]}"
        )

    badge = _load_badge(str(team_name))
    if badge is None:
        raise FileNotFoundError(
            f"No se encontró el escudo AJPA existente para {team_name!r}"
        )

    width, height = 1122, 1402
    image = Image.new("RGBA", (width, height), (8, 8, 10, 255))
    draw = ImageDraw.Draw(image, "RGBA")

    # Full-bleed dark stadium, matching the approved Fulham poster rather than
    # the previous generic card layout.
    for y in range(height):
        ratio = y / max(1, height - 1)
        shade = int(20 - 11 * ratio)
        draw.line((0, y, width, y), fill=(shade, shade, shade + 2, 255))

    # Side stands / banners.
    draw.polygon(
        [(0, 80), (245, 145), (300, 905), (0, 1060)],
        fill=(12, 12, 14, 245),
    )
    draw.polygon(
        [(width, 80), (width - 245, 145), (width - 300, 905), (width, 1060)],
        fill=(12, 12, 14, 245),
    )
    draw.line((244, 145, 300, 905), fill=(105, 108, 116, 55), width=3)
    draw.line((width - 244, 145, width - 300, 905), fill=(105, 108, 116, 55), width=3)

    # Crowd texture.
    for i in range(260):
        x = (i * 137 + 31) % width
        y = 510 + ((i * 73 + 19) % 430)
        if 275 < x < width - 275 and y < 720:
            continue
        level = 38 + (i % 5) * 9
        radius = 1 + (i % 3)
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(level, level, level + 2, 105),
        )

    # Stadium floodlights at the lower sides.
    for left in (True, False):
        base_x = 56 if left else width - 56
        direction = 1 if left else -1
        for row in range(4):
            for col in range(5):
                cx = base_x + direction * col * 24
                cy = 545 + row * 21
                draw.ellipse(
                    (cx - 6, cy - 6, cx + 6, cy + 6),
                    fill=(255, 249, 225, 235),
                )
        draw.line(
            (base_x, 625, base_x + direction * 95, 845),
            fill=(78, 79, 84, 170),
            width=7,
        )

    # Huge real club badge behind the trophy.
    badge = badge.convert("RGBA")
    badge.thumbnail((735, 735), Image.Resampling.LANCZOS)
    alpha = badge.getchannel("A").point(lambda value: int(value * 0.55))
    badge.putalpha(alpha)
    bx = (width - badge.width) // 2
    by = 55
    image.alpha_composite(badge, (bx, by))

    # Dark vignette keeps the crest integrated into the stadium.
    vignette = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vignette_draw = ImageDraw.Draw(vignette, "RGBA")
    for inset, opacity in ((0, 75), (35, 48), (75, 24)):
        vignette_draw.rounded_rectangle(
            (inset, inset, width - inset, height - inset),
            radius=80,
            outline=(0, 0, 0, opacity),
            width=45,
        )
    image = Image.alpha_composite(image, vignette)
    draw = ImageDraw.Draw(image, "RGBA")

    # Smoke, concentrated around the trophy base just like the reference.
    smoke = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    smoke_draw = ImageDraw.Draw(smoke, "RGBA")
    for i in range(18):
        cx = 95 + ((i * 127) % 930)
        cy = 590 + ((i * 57) % 285)
        rw = 95 + ((i * 31) % 115)
        rh = 45 + ((i * 23) % 75)
        smoke_draw.ellipse(
            (cx - rw, cy - rh, cx + rw, cy + rh),
            fill=(222, 222, 226, 20 + (i % 4) * 8),
        )
    smoke = smoke.filter(ImageFilter.GaussianBlur(30))
    image = Image.alpha_composite(image, smoke)
    draw = ImageDraw.Draw(image, "RGBA")

    # Competition-specific trophy. The source JPGs have their own dark
    # backgrounds, so derive a light subject mask from the image border and
    # soften/expand it. This removes the rectangular "photo card" effect.
    with Image.open(trophy_path) as source:
        trophy_rgb = source.convert("RGB")

    corners = [
        trophy_rgb.getpixel((2, 2)),
        trophy_rgb.getpixel((trophy_rgb.width - 3, 2)),
        trophy_rgb.getpixel((2, trophy_rgb.height - 3)),
        trophy_rgb.getpixel((trophy_rgb.width - 3, trophy_rgb.height - 3)),
    ]
    bg = tuple(sum(pixel[channel] for pixel in corners) // len(corners) for channel in range(3))
    flat = Image.new("RGB", trophy_rgb.size, bg)
    distance = ImageOps.grayscale(ImageChops.difference(trophy_rgb, flat))
    subject_alpha = distance.point(
        lambda value: 0 if value < 18 else 255 if value > 68 else int((value - 18) * 255 / 50)
    )
    subject_alpha = subject_alpha.filter(ImageFilter.MaxFilter(9))
    subject_alpha = subject_alpha.filter(ImageFilter.GaussianBlur(1.4))

    trophy = trophy_rgb.convert("RGBA")
    trophy.putalpha(subject_alpha)
    bbox = subject_alpha.getbbox()
    if bbox:
        trophy = trophy.crop(bbox)

    trophy.thumbnail((505, 555), Image.Resampling.LANCZOS)

    # Trophy shadow gives it the same foreground depth as the approved image.
    shadow = Image.new("RGBA", trophy.size, (0, 0, 0, 0))
    shadow.putalpha(
        trophy.getchannel("A")
        .filter(ImageFilter.GaussianBlur(14))
        .point(lambda value: int(value * 0.62))
    )
    tx = (width - trophy.width) // 2
    ty = 315
    image.alpha_composite(shadow, (tx + 10, ty + 22))
    image.alpha_composite(trophy, (tx, ty))

    # Black marble pedestal below the trophy.
    draw = ImageDraw.Draw(image, "RGBA")
    pedestal_top = [(365, 765), (757, 765), (810, 866), (312, 866)]
    draw.polygon(
        pedestal_top,
        fill=(14, 14, 16, 250),
        outline=(177, 178, 182, 145),
    )
    draw.rounded_rectangle(
        (246, 850, 876, 1010),
        radius=16,
        fill=(8, 8, 10, 252),
        outline=(124, 126, 132, 135),
        width=2,
    )
    # deterministic marble veins
    for i in range(17):
        x1 = 255 + ((i * 83) % 590)
        y1 = 865 + ((i * 29) % 120)
        x2 = min(870, x1 + 55 + (i % 5) * 22)
        y2 = min(1004, y1 + 10 + (i % 4) * 9)
        draw.line((x1, y1, x2, y2), fill=(155, 158, 166, 32), width=2)

    # Competition plate on the trophy pedestal.
    plate_label = {
        "league": "LIGA AJPA",
        "champions": "CHAMPIONS LEAGUE",
        "europa": "EUROPA LEAGUE",
    }[key]
    plate_w, plate_h = 310, 70
    plate_x = (width - plate_w) // 2
    plate_y = 805
    draw.rounded_rectangle(
        (plate_x, plate_y, plate_x + plate_w, plate_y + plate_h),
        radius=8,
        fill=(226, 226, 220, 235),
        outline=(245, 245, 240, 210),
        width=2,
    )
    plate_font = _fit_font(draw, plate_label, plate_w - 28, 24, 17, True)
    _center_text(
        draw,
        width,
        plate_y + 14,
        plate_label,
        plate_font,
        (24, 24, 26, 255),
    )
    season_plate = f"TEMPORADA {int(season_number)}"
    season_font = _fit_font(draw, season_plate, plate_w - 28, 18, 14, False)
    _center_text(
        draw,
        width,
        plate_y + 43,
        season_plate,
        season_font,
        (54, 54, 58, 255),
    )

    # Reference-style typography: club name is the dominant lower headline.
    club = str(team_name or "").strip().upper()
    subtitle = _SUBTITLES[key]
    manager = str(manager_name or "DT no registrado").strip() or "DT no registrado"
    bottom = f"{str(team_name).strip()} - {manager}"

    club_font = _fit_font(draw, club, 1010, 92, 47, True)
    subtitle_font = _fit_font(draw, subtitle, 1000, 45, 29, True)
    bottom_font = _fit_font(draw, bottom, 900, 35, 23, False)

    # Tiny shadow under text, then bright silver/white face.
    def headline(y, text, font, fill):
        box = draw.textbbox((0, 0), text, font=font)
        tw = box[2] - box[0]
        x = (width - tw) / 2
        draw.text((x + 3, y + 4), text, font=font, fill=(0, 0, 0, 205))
        draw.text((x, y), text, font=font, fill=fill)

    headline(1010, club, club_font, (245, 245, 245, 255))
    headline(1110, subtitle, subtitle_font, (238, 238, 240, 255))

    # Red separator from the approved Fulham composition.
    draw.rectangle((250, 1172, 872, 1176), fill=(150, 13, 24, 210))
    draw.rectangle((474, 1170, 648, 1179), fill=(220, 20, 36, 240))

    _center_text(draw, width, 1202, bottom, bottom_font, (218, 218, 221, 255))

    footer_font = _fit_font(
        draw,
        "DISCIPLINA  •  PASIÓN  •  COMUNIDAD",
        690,
        20,
        15,
        False,
    )
    _center_text(
        draw,
        width,
        1302,
        "DISCIPLINA  •  PASIÓN  •  COMUNIDAD",
        footer_font,
        (153, 153, 158, 235),
    )
    draw.rectangle((535, 1350, 587, 1354), fill=(218, 17, 33, 240))

    # Confetti is drawn last so it sits in the foreground like the reference.
    confetti = (
        (224, 23, 37, 225),
        (240, 240, 240, 220),
        (151, 154, 162, 195),
    )
    for i in range(70):
        x = 18 + ((i * 191) % 1080)
        y = 70 + ((i * 109) % 1050)
        if 430 < x < 690 and 315 < y < 805:
            continue
        w = 4 + (i % 4) * 2
        h = 9 + (i % 5) * 3
        draw.rounded_rectangle(
            (x, y, x + w, y + h),
            radius=2,
            fill=confetti[i % len(confetti)],
        )

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)

    # Release every large image object immediately after rendering.
    for obj in (
        badge,
        vignette,
        smoke,
        trophy_rgb,
        flat,
        distance,
        subject_alpha,
        trophy,
        shadow,
        image,
    ):
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
                    poster_version=?,posted_at=COALESCE(posted_at,CURRENT_TIMESTAMP)
                WHERE competition_id=?""",
            (
                int(guild_id),
                int(channel_id),
                int(message_id),
                _POSTER_VERSION,
                int(competition_id),
            ),
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
                    poster_version=?,posted_at=COALESCE(posted_at,CURRENT_TIMESTAMP)
                WHERE edition_id=? AND competition=?""",
            (
                int(guild_id),
                int(channel_id),
                int(message_id),
                _POSTER_VERSION,
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


async def _replace_existing_poster(
    message,
    filename: str,
    content: str,
    competition: str,
    team: str,
    manager_name: str,
    season_number: int,
) -> bool:
    payload = None
    try:
        payload = build_champion_poster(
            competition,
            team,
            manager_name,
            season_number,
        )
        replacement = discord.File(payload, filename=filename)
        await message.edit(
            content=content,
            attachments=[replacement],
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"AJPA champion Radio: no se pudo corregir message={getattr(message, 'id', None)}: {exc}"
        )
        return False
    except Exception as exc:
        print(
            f"AJPA champion Radio: render de corrección falló: "
            f"{type(exc).__name__}: {exc}"
        )
        return False
    finally:
        if payload is not None:
            try:
                payload.close()
            except Exception:
                pass
        gc.collect()


async def _upgrade_posted_posters(runtime, bot, guild) -> None:
    """Replace v1 champion attachments in place; never create a duplicate."""
    conn = league.db(runtime, int(guild.id))
    try:
        _ensure_schema(conn)
        season_jobs = [
            dict(row)
            for row in conn.execute(
                f"""SELECT * FROM {_SEASON_EVENTS}
                    WHERE guild_id=? AND status='posted'
                      AND COALESCE(poster_version,1)<?
                      AND channel_id IS NOT NULL
                      AND discord_message_id IS NOT NULL
                    ORDER BY competition_id""",
                (int(guild.id), _POSTER_VERSION),
            ).fetchall()
        ]
        cup_jobs = [
            dict(row)
            for row in conn.execute(
                f"""SELECT * FROM {_CUP_EVENTS}
                    WHERE guild_id=? AND status='posted'
                      AND COALESCE(poster_version,1)<?
                      AND channel_id IS NOT NULL
                      AND discord_message_id IS NOT NULL
                    ORDER BY edition_id,competition""",
                (int(guild.id), _POSTER_VERSION),
            ).fetchall()
        ]
    finally:
        conn.close()

    for job in season_jobs:
        conn = league.db(runtime, int(guild.id))
        try:
            valid = _validate_season_job(conn, job)
        finally:
            conn.close()
        if valid is None:
            continue

        champion, manager_name, season_number = valid
        channel = guild.get_channel(int(job["channel_id"]))
        if channel is None:
            continue
        try:
            message = await channel.fetch_message(int(job["discord_message_id"]))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            continue

        competition_id = int(job["competition_id"])
        filename = (
            f"ajpa-champion-league-s{season_number}-competition-{competition_id}.png"
        )
        content = (
            f"🏆 **{discord.utils.escape_markdown(champion)}** "
            "es el nuevo campeón de **Liga AJPA**."
        )
        if await _replace_existing_poster(
            message,
            filename,
            content,
            "league",
            champion,
            manager_name,
            season_number,
        ):
            conn = league.db(runtime, int(guild.id))
            try:
                conn.execute(
                    f"UPDATE {_SEASON_EVENTS} SET poster_version=? WHERE competition_id=?",
                    (_POSTER_VERSION, competition_id),
                )
                conn.commit()
            finally:
                conn.close()

    for job in cup_jobs:
        conn = league.db(runtime, int(guild.id))
        try:
            valid = _validate_cup_job(conn, job)
        finally:
            conn.close()
        if valid is None:
            continue

        champion, manager_name, season_number = valid
        channel = guild.get_channel(int(job["channel_id"]))
        if channel is None:
            continue
        try:
            message = await channel.fetch_message(int(job["discord_message_id"]))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            continue

        competition = str(job["competition"])
        edition_id = int(job["edition_id"])
        filename = (
            f"ajpa-champion-{competition}-s{season_number}-edition-{edition_id}.png"
        )
        content = (
            f"🏆 **{discord.utils.escape_markdown(champion)}** "
            f"es el nuevo campeón de **{_COMPETITION_NAMES[competition]}**."
        )
        if await _replace_existing_poster(
            message,
            filename,
            content,
            competition,
            champion,
            manager_name,
            season_number,
        ):
            conn = league.db(runtime, int(guild.id))
            try:
                conn.execute(
                    f"""UPDATE {_CUP_EVENTS}
                        SET poster_version=?
                        WHERE edition_id=? AND competition=?""",
                    (_POSTER_VERSION, edition_id, competition),
                )
                conn.commit()
            finally:
                conn.close()


async def _publish_pending(runtime, bot, guild) -> None:
    channel = await radio._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        return
    await _publish_seasons(runtime, bot, guild, channel)
    await _publish_cups(runtime, bot, guild, channel)
    await _upgrade_posted_posters(runtime, bot, guild)


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
        "(plantilla Fulham aprobada, cierre oficial, DT histórico, sin polling)"
    )
