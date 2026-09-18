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
import base64
import hashlib
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

_POSTER_VERSION = 6


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


def _poster_font(size: int, bold: bool = False, serif: bool = False):
    """Poster-only scalable font that is reliable on Railway slim images."""
    from PIL import ImageFont

    candidates = []
    if serif:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
                if bold
                else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
                "DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf",
            ]
        )
    candidates.extend(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        ]
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, int(size))
        except Exception:
            continue

    # Pillow 10+ ships a scalable default font. Passing size avoids the tiny
    # bitmap fallback that produced unreadable champion posters on Railway.
    try:
        return ImageFont.load_default(size=int(size))
    except TypeError:
        return ImageFont.load_default()


def _fit_font(
    draw,
    text: str,
    max_width: int,
    start: int,
    minimum: int,
    bold: bool = True,
    serif: bool = False,
):
    size = int(start)
    while size > minimum:
        font = _poster_font(size, bold=bold, serif=serif)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
        size -= 2
    return _poster_font(minimum, bold=bold, serif=serif)


def _center_text(draw, canvas_width: int, y: int, text: str, font, fill) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    draw.text(((canvas_width - width) / 2, y), text, font=font, fill=fill)


def _reference_cache_path() -> str:
    """Persistent decoded copy of the exact approved Fulham poster."""
    configured = str(os.getenv("AJPA_CHAMPION_REFERENCE_PATH") or "").strip()
    if configured:
        return configured
    if os.path.isdir("/data"):
        return "/data/ajpa_champion_reference_v6.jpg"
    return os.path.join(os.path.dirname(__file__), ".ajpa_champion_reference_v6.jpg")


_REFERENCE_CHUNK_DIR = "mobile/assets/trophies/fulham_reference_chunks"
_REFERENCE_CHUNK_COUNT = 9
_REFERENCE_SHA256 = "33f316b554c4eea93386a9c9c18596f5f5a0f097646f911952d2826ae9aa15cb"
_REFERENCE_SIZE = 29732


def _bundled_reference_payload() -> bytes:
    """Reassemble the exact approved reference that ships with the bot."""
    root = os.path.dirname(__file__)
    chunk_dir = os.path.join(root, _REFERENCE_CHUNK_DIR)
    encoded_parts = []
    for index in range(_REFERENCE_CHUNK_COUNT):
        chunk_path = os.path.join(chunk_dir, f"{index:02d}.txt")
        with open(chunk_path, "r", encoding="ascii") as handle:
            encoded_parts.append("".join(handle.read().split()))
    payload = base64.b64decode("".join(encoded_parts), validate=True)
    if len(payload) != _REFERENCE_SIZE:
        raise RuntimeError(
            f"Plantilla Fulham incompleta: {len(payload)} bytes; esperados {_REFERENCE_SIZE}."
        )
    digest = hashlib.sha256(payload).hexdigest()
    if digest != _REFERENCE_SHA256:
        raise RuntimeError(
            "La plantilla Fulham empaquetada no coincide con el archivo aprobado."
        )
    if not payload.startswith(b"\xff\xd8"):
        raise RuntimeError("La plantilla Fulham empaquetada no es un JPEG válido.")
    return payload


def _reference_is_usable(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    try:
        with open(path, "rb") as handle:
            payload = handle.read()
        if len(payload) != _REFERENCE_SIZE:
            return False
        if hashlib.sha256(payload).hexdigest() != _REFERENCE_SHA256:
            return False
        from PIL import Image, ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        with Image.open(io.BytesIO(payload)) as source:
            width, height = source.size
            return width == 500 and height == 625
    except Exception:
        return False


def _ensure_bundled_reference() -> str:
    """Install the approved poster on the Railway volume; never guess from Discord."""
    path = _reference_cache_path()
    if _reference_is_usable(path):
        return path

    payload = _bundled_reference_payload()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as handle:
        handle.write(payload)
    os.replace(tmp, path)

    if not _reference_is_usable(path):
        raise RuntimeError("No se pudo validar la plantilla Fulham después de instalarla.")

    print(
        "AJPA champion Radio: plantilla Fulham APROBADA cargada desde el proyecto "
        f"-> {path} sha256={_REFERENCE_SHA256[:12]}"
    )
    return path


async def _ensure_reference_template(channel) -> str | None:
    """Return only the bundled approved Fulham poster.

    Deliberately ignores Discord history: a standings image was once mistaken
    for the poster because it contained the same team/competition words.
    """
    try:
        return await asyncio.to_thread(_ensure_bundled_reference)
    except Exception as exc:
        print(
            "AJPA champion Radio: plantilla aprobada no disponible: "
            f"{type(exc).__name__}: {exc}"
        )
        return None


def _feather_box_mask(size, box, feather=42):
    from PIL import Image, ImageDraw, ImageFilter

    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(box, radius=max(18, feather), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(feather))


def _cover_variable_area(image, box, blur_radius=28, darken=0.44, feather=36):
    """Hide only the old variable layer while preserving the real poster texture."""
    from PIL import Image, ImageEnhance, ImageFilter

    x0, y0, x1, y1 = [int(v) for v in box]
    crop = image.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(blur_radius))
    crop = ImageEnhance.Brightness(crop).enhance(float(darken))
    softened = image.copy()
    softened.alpha_composite(crop, (x0, y0))
    mask = _feather_box_mask(image.size, box, feather)
    result = Image.composite(softened, image, mask)
    try:
        crop.close()
        softened.close()
        mask.close()
    except Exception:
        pass
    return result


def build_champion_poster(
    competition_type,
    team_name,
    manager_name,
    season_number,
    template_path=None,
):
    """Composite the winner over the exact published Fulham poster.

    No stadium, background, crowd, confetti or poster frame is redrawn here.
    The original publication is the master image. We touch only the variable
    crest/trophy/text zones and paste the real AJPA badge + official trophy.
    """
    key = str(competition_type or "").strip().lower()
    if key not in _TROPHY_FILES:
        raise ValueError(f"Competencia de campeón inválida: {competition_type!r}")
    if not template_path or not _reference_is_usable(str(template_path)):
        raise FileNotFoundError(
            "No está disponible la publicación original de Fulham para usarla como plantilla."
        )

    from PIL import Image, ImageDraw, ImageFilter, ImageFile
    # Some of the historical AJPA trophy JPG assets were saved aggressively
    # and Pillow can flag their final scan as truncated even though browsers
    # render them correctly. Accept those exact source pixels instead of
    # regenerating/re-encoding the trophy artwork.
    ImageFile.LOAD_TRUNCATED_IMAGES = True

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

    with Image.open(str(template_path)) as source:
        image = source.convert("RGBA")

    # Keep the exact poster aspect ratio and pixels, only normalizing output size.
    width, height = 1122, 1402
    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.LANCZOS)

    # Old Fulham crest + preseason trophy occupy the central variable zone.
    # Blur/darken those exact pixels instead of inventing a new background.
    covered = _cover_variable_area(
        image,
        (205, 28, 918, 925),
        blur_radius=33,
        darken=0.40,
        feather=48,
    )
    image.close()
    image = covered

    # Old FULHAM / subtitle / DT copy is another variable layer.
    covered = _cover_variable_area(
        image,
        (70, 930, 1052, 1268),
        blur_radius=24,
        darken=0.28,
        feather=34,
    )
    image.close()
    image = covered

    # Winner crest: the actual existing AJPA team asset, enlarged behind the cup.
    badge = badge.convert("RGBA")
    bbox = badge.getchannel("A").getbbox()
    if bbox:
        badge = badge.crop(bbox)
    badge_target = 710
    scale = badge_target / max(1, max(badge.width, badge.height))
    badge = badge.resize(
        (
            max(1, int(round(badge.width * scale))),
            max(1, int(round(badge.height * scale))),
        ),
        Image.Resampling.LANCZOS,
    )
    alpha = badge.getchannel("A").point(lambda value: int(value * 0.72))
    badge.putalpha(alpha)
    image.alpha_composite(badge, ((width - badge.width) // 2, 42))

    # Official trophy source. These are the exact AJPA trophy images already
    # stored in the repo; their background is removed at runtime, no AI redraw.
    with Image.open(trophy_path) as source:
        trophy_rgb = source.convert("RGB")

    # Robust black/dark-background removal. The original trophy itself remains
    # untouched; only background pixels become transparent.
    corners = [
        trophy_rgb.getpixel((2, 2)),
        trophy_rgb.getpixel((trophy_rgb.width - 3, 2)),
        trophy_rgb.getpixel((2, trophy_rgb.height - 3)),
        trophy_rgb.getpixel((trophy_rgb.width - 3, trophy_rgb.height - 3)),
    ]
    bg = tuple(
        sum(pixel[channel] for pixel in corners) // len(corners)
        for channel in range(3)
    )
    from PIL import ImageChops, ImageOps
    flat = Image.new("RGB", trophy_rgb.size, bg)
    distance = ImageOps.grayscale(ImageChops.difference(trophy_rgb, flat))
    subject_alpha = distance.point(
        lambda value: 0 if value < 15
        else 255 if value > 54
        else int((value - 15) * 255 / 39)
    )
    subject_alpha = subject_alpha.filter(ImageFilter.MaxFilter(7))
    subject_alpha = subject_alpha.filter(ImageFilter.GaussianBlur(1.1))

    trophy = trophy_rgb.convert("RGBA")
    trophy.putalpha(subject_alpha)
    crop_box = subject_alpha.getbbox()
    if crop_box:
        trophy = trophy.crop(crop_box)

    trophy_limits = {
        "league": (500, 600),
        "champions": (515, 610),
        "europa": (445, 610),
    }[key]
    trophy.thumbnail(trophy_limits, Image.Resampling.LANCZOS)

    shadow = Image.new("RGBA", trophy.size, (0, 0, 0, 0))
    shadow.putalpha(
        trophy.getchannel("A")
        .filter(ImageFilter.GaussianBlur(13))
        .point(lambda value: int(value * 0.58))
    )
    tx = (width - trophy.width) // 2
    ty = {
        "league": 325,
        "champions": 315,
        "europa": 305,
    }[key]
    image.alpha_composite(shadow, (tx + 8, ty + 17))
    image.alpha_composite(trophy, (tx, ty))

    draw = ImageDraw.Draw(image, "RGBA")

    # Only the variable copy is redrawn; the poster itself remains the original.
    club = str(team_name or "").strip().upper()
    subtitle = _SUBTITLES[key]
    manager = str(manager_name or "DT no registrado").strip() or "DT no registrado"
    bottom = f"{str(team_name).strip()} - {manager}"

    club_font = _fit_font(draw, club, 1010, 104, 50, True, serif=True)
    subtitle_font = _fit_font(draw, subtitle, 1010, 48, 29, True, serif=True)
    bottom_font = _fit_font(draw, bottom, 900, 37, 23, False)

    def headline(y, text, font, fill):
        box = draw.textbbox((0, 0), text, font=font)
        tw = box[2] - box[0]
        x = (width - tw) / 2
        draw.text((x + 4, y + 5), text, font=font, fill=(0, 0, 0, 230))
        draw.text((x + 1, y + 1), text, font=font, fill=(104, 104, 108, 225))
        draw.text((x, y), text, font=font, fill=fill)

    headline(963, club, club_font, (248, 248, 248, 255))
    headline(1081, subtitle, subtitle_font, (238, 238, 240, 255))

    # Keep the reference poster's red identity line while replacing only copy.
    draw.rectangle((238, 1161, 884, 1165), fill=(126, 8, 18, 220))
    draw.rectangle((462, 1159, 660, 1168), fill=(226, 18, 33, 245))
    _center_text(draw, width, 1198, bottom, bottom_font, (226, 226, 230, 255))

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)

    for obj in (
        badge,
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

def _validate_composites_once(template_path: str) -> None:
    """Dry-run the three official cups once on the persistent Railway volume."""
    marker = str(template_path) + f".poster-v{_POSTER_VERSION}.ok"
    if os.path.isfile(marker):
        return

    for competition in ("league", "champions", "europa"):
        try:
            payload = build_champion_poster(
                competition,
                "Fulham",
                "CyclopsMVG",
                1,
                template_path=template_path,
            )
        except Exception as exc:
            raise RuntimeError(
                f"{competition}: {type(exc).__name__}: {exc}"
            ) from exc
        try:
            head = payload.read(8)
            if head != b"\x89PNG\r\n\x1a\n":
                raise RuntimeError(
                    f"El render de {competition} no produjo un PNG válido."
                )
            payload.seek(0, os.SEEK_END)
            if payload.tell() < 40_000:
                raise RuntimeError(
                    f"El render de {competition} quedó anormalmente pequeño."
                )
        finally:
            payload.close()

    with open(marker, "w", encoding="utf-8") as handle:
        handle.write("ok\n")
    print(
        "AJPA champion Radio: composición exacta validada en seco "
        "(Liga + Champions + Europa, sin publicar)."
    )


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
        template_path = await _ensure_reference_template(channel)
        if not template_path:
            print("AJPA champion Radio: publicación aplazada; falta plantilla maestra.")
            return None
        payload = build_champion_poster(
            competition,
            team,
            manager_name,
            season_number,
            template_path=template_path,
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
        template_path = await _ensure_reference_template(message.channel)
        if not template_path:
            return False
        payload = build_champion_poster(
            competition,
            team,
            manager_name,
            season_number,
            template_path=template_path,
        )
        replacement = discord.File(payload, filename=filename)
        await message.edit(
            content=content,
            attachments=[replacement],
            allowed_mentions=discord.AllowedMentions.none(),
        )
        print(
            "AJPA champion Radio: póster corregido in-place "
            f"message={getattr(message, 'id', None)} competition={competition} "
            f"team={team!r} version={_POSTER_VERSION}"
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
    # Prewarm the exact published Fulham poster even when there is no pending
    # final yet, so closing a competition never has to discover it at that moment.
    template_path = await _ensure_reference_template(channel)
    if template_path:
        try:
            await asyncio.to_thread(_validate_composites_once, template_path)
        except Exception as exc:
            print(
                "AJPA champion Radio: validación de composición falló: "
                f"{type(exc).__name__}: {exc}"
            )
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
