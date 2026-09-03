"""Radio Pasillo: anuncia únicamente adelantamientos reales dentro del Top 5.

La capa se monta sobre el feedback final de Liga. Toma una foto lógica de la
tabla antes de procesar un resultado nuevo y la compara con la tabla oficial
después de persistirlo. Solo crea un evento cuando un club que YA estaba en el
Top 5 termina en una posición mejor y deja debajo a otro club que también
estaba en ese Top 5.

Cada evento se guarda antes de enviarse para poder reintentar tras un reinicio
sin duplicar publicaciones. La imagen se genera localmente con Pillow y usa los
escudos incluidos en AJPA Mobile; no depende de servicios externos.
"""

from __future__ import annotations

import io
import json
import os
import unicodedata
from typing import Any

import discord
from PIL import Image, ImageDraw, ImageFont

import league_automation_patch as league
import league_result_feedback_patch as feedback


_BASE_FEEDBACK_HANDLE = feedback._feedback_handle
_BASE_FEEDBACK_APPLY = feedback.apply_league_result_feedback_patch

_EVENT_TABLE = "league_top5_radio_events"


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
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_EVENT_TABLE} (
            source_message_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            moves_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            channel_id INTEGER,
            discord_message_id INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            posted_at DATETIME
        )
        """
    )
    conn.commit()


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        data = dict(row)
    else:
        try:
            data = dict(row)
        except Exception:
            data = {}
    team = str(data.get("team") or data.get("club") or data.get("name") or "").strip()
    gf = int(data.get("gf") or 0)
    gc = int(data.get("gc") or 0)
    dg = data.get("dg")
    if dg is None:
        dg = data.get("gd")
    if dg is None:
        dg = gf - gc
    return {
        "team": team,
        "pj": int(data.get("pj") or 0),
        "pg": int(data.get("pg") or 0),
        "pe": int(data.get("pe") or 0),
        "pp": int(data.get("pp") or 0),
        "gf": gf,
        "gc": gc,
        "dg": int(dg or 0),
        "pts": int(data.get("pts") or data.get("points") or 0),
    }


def _top5(runtime, guild_id: int) -> list[dict[str, Any]]:
    conn = league.db(runtime, int(guild_id))
    try:
        rows = league.standings(conn)
        return [_row_dict(row) for row in list(rows)[:5]]
    finally:
        conn.close()


def _source_exists(runtime, guild_id: int, source_message_id: int) -> bool:
    conn = league.db(runtime, int(guild_id))
    try:
        if not _table_exists(conn, "league_matches"):
            return False
        return bool(
            conn.execute(
                "SELECT 1 FROM league_matches WHERE source_message_id=? LIMIT 1",
                (int(source_message_id),),
            ).fetchone()
        )
    finally:
        conn.close()


def _detect_overtakes(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    before_pos = {_team_key(row["team"]): idx + 1 for idx, row in enumerate(before)}
    after_pos = {_team_key(row["team"]): idx + 1 for idx, row in enumerate(after)}
    before_by_key = {_team_key(row["team"]): row for row in before}
    moves: list[dict[str, Any]] = []

    # Regla AJPA estricta: el club que sube tenía que estar ya dentro del Top 5.
    for current in after:
        key = _team_key(current["team"])
        old_pos = before_pos.get(key)
        new_pos = after_pos.get(key)
        if old_pos is None or new_pos is None or new_pos >= old_pos:
            continue

        passed: list[dict[str, Any]] = []
        for other_key, other_old_pos in before_pos.items():
            if other_key == key:
                continue
            other_new_pos = after_pos.get(other_key)
            # Antes estaba arriba del que subió y ahora quedó por debajo.
            if (
                other_old_pos < old_pos
                and other_new_pos is not None
                and other_new_pos > new_pos
            ):
                other = before_by_key.get(other_key)
                if other:
                    passed.append(
                        {
                            "team": str(other["team"]),
                            "old_pos": int(other_old_pos),
                            "new_pos": int(other_new_pos),
                        }
                    )

        if passed:
            passed.sort(key=lambda item: item["old_pos"])
            moves.append(
                {
                    "team": str(current["team"]),
                    "old_pos": int(old_pos),
                    "new_pos": int(new_pos),
                    "passed": passed,
                }
            )

    moves.sort(key=lambda item: (item["new_pos"], item["old_pos"]))
    return moves


def _store_event(
    runtime,
    guild_id: int,
    source_message_id: int,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    moves: list[dict[str, Any]],
) -> None:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {_EVENT_TABLE}
                (source_message_id, guild_id, before_json, after_json, moves_json, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (
                int(source_message_id),
                int(guild_id),
                json.dumps(before, ensure_ascii=False, separators=(",", ":")),
                json.dumps(after, ensure_ascii=False, separators=(",", ":")),
                json.dumps(moves, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _event(runtime, guild_id: int, source_message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        return conn.execute(
            f"SELECT * FROM {_EVENT_TABLE} WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
    finally:
        conn.close()


def _mark_posted(
    runtime,
    guild_id: int,
    source_message_id: int,
    channel_id: int,
    discord_message_id: int,
) -> None:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""
            UPDATE {_EVENT_TABLE}
            SET status='posted', channel_id=?, discord_message_id=?,
                posted_at=CURRENT_TIMESTAMP
            WHERE source_message_id=?
            """,
            (int(channel_id), int(discord_message_id), int(source_message_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _normalized_channel_name(name: str) -> str:
    return "".join(ch for ch in str(name or "").casefold() if ch.isalnum())


async def _resolve_radio_channel(runtime, bot, guild):
    if guild is None:
        return None

    configured_id = None
    conn = league.db(runtime, int(guild.id))
    try:
        if _table_exists(conn, "public_market_channels"):
            row = conn.execute(
                "SELECT channel_id FROM public_market_channels WHERE guild_id=? LIMIT 1",
                (int(guild.id),),
            ).fetchone()
            configured_id = int(row["channel_id"]) if row and row["channel_id"] else None
    finally:
        conn.close()

    if configured_id:
        channel = guild.get_channel(configured_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(configured_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None
        if channel is not None and hasattr(channel, "send"):
            return channel

    me = getattr(guild, "me", None)
    for channel in getattr(guild, "text_channels", []):
        if "radiopasillo" not in _normalized_channel_name(getattr(channel, "name", "")):
            continue
        if me is not None:
            try:
                perms = channel.permissions_for(me)
                if not perms.view_channel or not perms.send_messages:
                    continue
            except Exception:
                pass
        return channel
    return None


def _club_emoji(guild, club: str) -> str:
    try:
        import team_badge_selector_patch as selector
        import team_badges_patch as badges

        candidates = [str(club or "").strip()]
        aliases = getattr(badges, "ALIASES", {}) or {}
        alias = aliases.get(_norm(club))
        if alias:
            candidates.append(str(alias))
        try:
            canonical = league.canonical_team(club)
            if canonical:
                candidates.append(str(canonical))
        except Exception:
            pass

        seen = set()
        for candidate in candidates:
            marker = _norm(candidate)
            if not marker or marker in seen:
                continue
            seen.add(marker)
            emoji = selector._find_badge_emoji(guild, candidate)
            if emoji is not None:
                return str(emoji)
    except Exception:
        pass
    return "⚽"


_BADGE_FILES = {
    "ajax": "ajax.png",
    "asmonaco": "as_monaco.png",
    "monaco": "as_monaco.png",
    "astonvilla": "aston_villa.png",
    "atleticomadrid": "atletico_madrid.png",
    "benfica": "benfica.png",
    "boltonwanderers": "bolton_wanderers.png",
    "bolton": "bolton_wanderers.png",
    "everton": "everton.png",
    "feyenoord": "feyenoord.png",
    "fiorentina": "fiorentina.png",
    "fulham": "fulham.png",
    "galatasaray": "galatasaray.png",
    "lazio": "lazio.png",
    "manchestercity": "manchester_city.png",
    "middlesbrough": "middlesbrough.png",
    "olympiquelyon": "olympique_lyon.png",
    "lyon": "olympique_lyon.png",
    "olympiquemarseille": "olympique_marseille.png",
    "olympiquedemarseille": "olympique_marseille.png",
    "marsella": "olympique_marseille.png",
    "porto": "porto.png",
    "psg": "psg.png",
    "parissaintgermain": "psg.png",
    "realbetis": "real_betis.png",
    "betis": "real_betis.png",
    "sevilla": "sevilla.png",
    "torino": "torino.png",
    "tottenhamhotspur": "tottenham_hotspur.png",
    "tottenham": "tottenham_hotspur.png",
    "villarreal": "villarreal.png",
    "villareal": "villarreal.png",
    "westhamunited": "west_ham_united.png",
    "westham": "west_ham_united.png",
    "zaragoza": "zaragoza.png",
}


def _asset_path(team: str) -> str | None:
    keys = [_team_key(team), _norm(team)]
    for key in keys:
        filename = _BADGE_FILES.get(key)
        if not filename:
            continue
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "mobile",
            "assets",
            "teams",
            filename,
        )
        if os.path.isfile(path):
            return path
    return None


def _font(size: int, bold: bool = False):
    names = (
        ["DejaVuSans-Bold.ttf", "Arial Bold.ttf"]
        if bold
        else ["DejaVuSans.ttf", "Arial.ttf"]
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _fit_text(draw, text: str, font, max_width: int) -> str:
    value = str(text)
    if draw.textbbox((0, 0), value, font=font)[2] <= max_width:
        return value
    while len(value) > 3:
        value = value[:-1]
        candidate = value.rstrip() + "…"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            return candidate
    return value


def _render_top5(after: list[dict[str, Any]]) -> io.BytesIO:
    width, height = 1200, 860
    image = Image.new("RGB", (width, height), (13, 16, 24))
    draw = ImageDraw.Draw(image)

    # Encabezado inspirado en la pantalla Liga de AJPA: oscuro, limpio y legible.
    draw.rounded_rectangle((42, 38, width - 42, height - 38), radius=34, fill=(24, 29, 42))
    draw.rounded_rectangle((42, 38, width - 42, 172), radius=34, fill=(35, 42, 59))
    draw.rectangle((42, 138, width - 42, 172), fill=(35, 42, 59))

    title_font = _font(52, bold=True)
    sub_font = _font(25)
    header_font = _font(23, bold=True)
    row_font = _font(30, bold=True)
    stat_font = _font(28, bold=True)
    pos_font = _font(34, bold=True)

    draw.text((82, 66), "LIGA", font=title_font, fill=(246, 248, 252))
    draw.text((82, 126), "TOP 5 • TABLA ACTUALIZADA", font=sub_font, fill=(178, 187, 207))

    y_header = 194
    draw.text((84, y_header), "#", font=header_font, fill=(152, 162, 184))
    draw.text((215, y_header), "EQUIPO", font=header_font, fill=(152, 162, 184))
    draw.text((845, y_header), "PJ", font=header_font, fill=(152, 162, 184))
    draw.text((955, y_header), "DG", font=header_font, fill=(152, 162, 184))
    draw.text((1070, y_header), "PTS", font=header_font, fill=(152, 162, 184))

    row_top = 238
    row_h = 112
    for idx, row in enumerate(after[:5], start=1):
        y = row_top + (idx - 1) * row_h
        fill = (30, 36, 51) if idx % 2 else (27, 33, 47)
        draw.rounded_rectangle((68, y, width - 68, y + 94), radius=22, fill=fill)

        pos = str(idx)
        pos_box = draw.textbbox((0, 0), pos, font=pos_font)
        pos_w = pos_box[2] - pos_box[0]
        draw.text((113 - pos_w / 2, y + 25), pos, font=pos_font, fill=(244, 246, 250))

        badge_path = _asset_path(str(row["team"]))
        if badge_path:
            try:
                badge = Image.open(badge_path).convert("RGBA")
                badge.thumbnail((66, 66), Image.Resampling.LANCZOS)
                bx = 170 - badge.width // 2
                by = y + 47 - badge.height // 2
                image.paste(badge, (bx, by), badge)
            except Exception:
                pass

        name = _fit_text(draw, str(row["team"]), row_font, 540)
        draw.text((215, y + 28), name, font=row_font, fill=(246, 248, 252))
        draw.text((850, y + 30), str(int(row["pj"])), font=stat_font, fill=(225, 229, 238))

        dg = int(row["dg"])
        dg_text = f"+{dg}" if dg > 0 else str(dg)
        draw.text((947, y + 30), dg_text, font=stat_font, fill=(225, 229, 238))
        draw.text((1070, y + 27), str(int(row["pts"])), font=pos_font, fill=(255, 255, 255))

    draw.text(
        (82, height - 82),
        "AJPA • Radio Pasillo",
        font=_font(21, bold=True),
        fill=(143, 153, 174),
    )

    payload = io.BytesIO()
    image.save(payload, format="PNG", optimize=True)
    payload.seek(0)
    return payload


def _ordinal(position: int) -> str:
    return f"{int(position)}.º"


def _join_team_mentions(guild, passed: list[dict[str, Any]]) -> str:
    parts = []
    for item in passed:
        name = discord.utils.escape_markdown(str(item["team"]))
        parts.append(f"{_club_emoji(guild, str(item['team']))} **{name}**")
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return ", ".join(parts[:-1]) + " y " + parts[-1]


def _announcement_text(guild, moves: list[dict[str, Any]]) -> str:
    lines = [
        "📻 **R A D I O - P A S I L L O**",
        "🚨 **MOVIMIENTO EN EL TOP 5**",
        "",
    ]
    for move in moves:
        team = discord.utils.escape_markdown(str(move["team"]))
        emoji = _club_emoji(guild, str(move["team"]))
        passed = _join_team_mentions(guild, list(move.get("passed") or []))
        lines.append(
            f"🔥 {emoji} **{team}** pasó del **{_ordinal(move['old_pos'])}** "
            f"al **{_ordinal(move['new_pos'])}** y superó a {passed}."
        )
    return "\n".join(lines)


async def _publish_event(runtime, bot, guild, source_message_id: int) -> bool:
    row = _event(runtime, guild.id, int(source_message_id))
    if not row:
        return False
    if str(row["status"] or "").casefold() == "posted":
        return True

    channel = await _resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(
            f"AJAP Top5 Radio pendiente mensaje={source_message_id}: Radio Pasillo no encontrado"
        )
        return False

    try:
        after = json.loads(str(row["after_json"]))
        moves = json.loads(str(row["moves_json"]))
    except Exception as exc:
        print(f"AJAP Top5 Radio payload inválido mensaje={source_message_id}: {exc}")
        return False

    image = _render_top5(after)
    file = discord.File(image, filename=f"ajpa-liga-top5-{int(source_message_id)}.png")
    try:
        sent = await channel.send(
            content=_announcement_text(guild, moves),
            file=file,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"AJAP Top5 Radio envío falló mensaje={source_message_id} "
            f"canal={getattr(channel, 'id', None)}: {exc}"
        )
        return False

    _mark_posted(runtime, guild.id, source_message_id, channel.id, sent.id)
    print(
        f"AJAP Top5 Radio publicado mensaje={source_message_id} "
        f"canal={channel.id} movimientos={len(moves)}"
    )
    return True


async def _publish_pending(runtime, bot, guild) -> None:
    conn = league.db(runtime, int(guild.id))
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            f"""
            SELECT source_message_id
            FROM {_EVENT_TABLE}
            WHERE status='pending'
            ORDER BY created_at
            LIMIT 50
            """
        ).fetchall()
        ids = [int(row["source_message_id"]) for row in rows]
    finally:
        conn.close()

    for source_id in ids:
        try:
            await _publish_event(runtime, bot, guild, source_id)
        except Exception as exc:
            print(
                f"AJAP Top5 Radio retry falló guild={guild.id} "
                f"mensaje={source_id}: {exc}"
            )


async def _feedback_handle_with_top5_radio(runtime, bot, message):
    guild = getattr(message, "guild", None)
    author = getattr(message, "author", None)
    source_id = int(getattr(message, "id", 0) or 0)

    before = None
    is_new_source = False
    if guild is not None and source_id and not bool(getattr(author, "bot", False)):
        try:
            is_new_source = not _source_exists(runtime, guild.id, source_id)
            if is_new_source:
                before = _top5(runtime, guild.id)
        except Exception as exc:
            print(
                f"AJAP Top5 Radio snapshot previo falló guild={guild.id} "
                f"mensaje={source_id}: {exc}"
            )

    result = await _BASE_FEEDBACK_HANDLE(runtime, bot, message)

    if guild is None or not source_id or before is None or not is_new_source:
        return result

    try:
        # Solo una persistencia oficial nueva puede mover la tabla.
        if not _source_exists(runtime, guild.id, source_id):
            return result

        after = _top5(runtime, guild.id)
        moves = _detect_overtakes(before, after)
        if not moves:
            return result

        _store_event(runtime, guild.id, source_id, before, after, moves)
        await _publish_event(runtime, bot, guild, source_id)
    except Exception as exc:
        # Radio Pasillo nunca debe romper la carga oficial del resultado.
        print(
            f"AJAP Top5 Radio post-carga falló guild={guild.id} "
            f"mensaje={source_id}: {exc}"
        )
    return result


# El diagnóstico de Liga considera sano al handler cuando conserva este nombre.
_feedback_handle_with_top5_radio.__name__ = "_feedback_handle"
feedback._feedback_handle = _feedback_handle_with_top5_radio


def _apply_feedback_with_top5_radio(runtime, bot):
    _BASE_FEEDBACK_APPLY(runtime, bot)

    feedback._feedback_handle = _feedback_handle_with_top5_radio
    league.handle = _feedback_handle_with_top5_radio

    if getattr(runtime, "_ajap_top5_radio_ready", False):
        return

    async def ready_listener():
        for guild in list(getattr(bot, "guilds", [])):
            try:
                await _publish_pending(runtime, bot, guild)
            except Exception as exc:
                print(f"AJAP Top5 Radio outbox guild={guild.id}: {exc}")

    bot.add_listener(ready_listener, "on_ready")
    runtime._ajap_top5_radio_ready = True
    print(
        "AJAP Radio Pasillo: adelantamientos Top 5 activos "
        "(solo subidas reales dentro del Top 5 + imagen local)"
    )


feedback.apply_league_result_feedback_patch = _apply_feedback_with_top5_radio
