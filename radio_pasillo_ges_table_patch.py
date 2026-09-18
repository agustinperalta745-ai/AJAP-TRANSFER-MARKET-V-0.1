"""Publish the complete official AJPA standings in Radio Pasillo after every manual GES sync.

Staff's "GES actualizada" action remains the only trigger.  Each successful sync
stores a recoverable Radio Pasillo event, renders the complete table locally,
and posts a short piece of commentary based on what changed in the standings.
"""

from __future__ import annotations

import io
import json
import os
import re
from typing import Any

import discord

import guild_isolation_patch as guild_isolation
import league_ges_manual_sync_patch as ges
import season_ges_authority_patch as seasonal
import league_top5_overtake_radio_patch as top5


_EVENT_TABLE = "radio_pasillo_ges_table_events"


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _ensure_schema(conn) -> None:
    ges._ensure_schema(conn)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_EVENT_TABLE} (
            sync_run_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            league_id TEXT NOT NULL,
            competition_label TEXT NOT NULL DEFAULT '',
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
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
    data = dict(row) if not isinstance(row, dict) else dict(row)
    gf = int(data.get("gf") or 0)
    gc = int(data.get("gc") or 0)
    dg = data.get("dg")
    if dg is None:
        dg = gf - gc
    return {
        "position": int(data.get("position") or 0),
        "team": str(data.get("team") or "").strip(),
        "pts": int(data.get("pts") or 0),
        "pj": int(data.get("pj") or 0),
        "pg": int(data.get("pg") or 0),
        "pe": int(data.get("pe") or 0),
        "pp": int(data.get("pp") or 0),
        "gf": gf,
        "gc": gc,
        "dg": int(dg or 0),
    }


def _standings(runtime, guild_id: int, league_id: str) -> list[dict[str, Any]]:
    league_id = str(league_id or "").strip()
    if not league_id:
        return []
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            """SELECT position,team,pts,pj,pg,pe,pp,gf,gc,dg
               FROM league_ges_standings
               WHERE guild_id=? AND league_id=?
               ORDER BY position ASC, team COLLATE NOCASE ASC""",
            (int(guild_id), league_id),
        ).fetchall()
        return [_row_dict(row) for row in rows]
    finally:
        conn.close()


def _latest_sync_run_id(runtime, guild_id: int, league_id: str) -> int | None:
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        row = conn.execute(
            """SELECT id FROM league_ges_sync_runs
               WHERE guild_id=? AND league_id=?
               ORDER BY id DESC LIMIT 1""",
            (int(guild_id), str(league_id)),
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()


def _store_event(
    runtime,
    guild_id: int,
    sync_run_id: int,
    league_id: str,
    competition_label: str,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> None:
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""INSERT OR IGNORE INTO {_EVENT_TABLE}
                   (sync_run_id,guild_id,league_id,competition_label,before_json,after_json,status)
               VALUES(?,?,?,?,?,?,'pending')""",
            (
                int(sync_run_id),
                int(guild_id),
                str(league_id),
                str(competition_label or ""),
                json.dumps(before, ensure_ascii=False, separators=(",", ":")),
                json.dumps(after, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _event(runtime, guild_id: int, sync_run_id: int):
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        return conn.execute(
            f"SELECT * FROM {_EVENT_TABLE} WHERE sync_run_id=? AND guild_id=? LIMIT 1",
            (int(sync_run_id), int(guild_id)),
        ).fetchone()
    finally:
        conn.close()


def _mark_posted(
    runtime,
    guild_id: int,
    sync_run_id: int,
    channel_id: int,
    message_id: int,
) -> None:
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""UPDATE {_EVENT_TABLE}
                SET status='posted', channel_id=?, discord_message_id=?,
                    posted_at=CURRENT_TIMESTAMP
                WHERE sync_run_id=? AND guild_id=?""",
            (int(channel_id), int(message_id), int(sync_run_id), int(guild_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _position_map(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for index, row in enumerate(rows, start=1):
        key = top5._team_key(row.get("team"))
        if key:
            out[key] = int(row.get("position") or index)
    return out


def _safe_team(team: str) -> str:
    return discord.utils.escape_markdown(str(team or "").strip())


def _ordinal(value: int) -> str:
    return f"{int(value)}.º"


def _commentary(
    guild,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> str:
    lines = [
        "📻 **R A D I O - P A S I L L O**",
        "📊 **TABLA ACTUALIZADA**",
        "",
    ]
    if not after:
        lines.append("GES se sincronizó, pero no quedó una tabla disponible para mostrar.")
        return "\n".join(lines)

    leader = after[0]
    runner = after[1] if len(after) > 1 else None
    leader_name = _safe_team(leader["team"])
    leader_badge = top5._club_emoji(guild, leader["team"])

    old_positions = _position_map(before)
    new_positions = _position_map(after)
    old_leader_key = top5._team_key(before[0]["team"]) if before else ""
    new_leader_key = top5._team_key(leader["team"])

    if not before:
        lines.append(
            f"🆕 Primera foto oficial de esta tabla: {leader_badge} **{leader_name}** "
            f"arranca arriba con **{leader['pts']} pts**."
        )
    elif old_leader_key and old_leader_key != new_leader_key:
        old_leader = _safe_team(before[0]["team"])
        lines.append(
            f"🚨 **Hay nuevo puntero.** {leader_badge} **{leader_name}** tomó la cima "
            f"y dejó atrás a **{old_leader}**."
        )
    else:
        climbs = []
        drops = []
        for row in after:
            key = top5._team_key(row["team"])
            if key not in old_positions:
                continue
            new_pos = new_positions.get(key)
            old_pos = old_positions.get(key)
            if new_pos is None or old_pos is None:
                continue
            delta = int(old_pos) - int(new_pos)
            if delta > 0:
                climbs.append((delta, old_pos, new_pos, row))
            elif delta < 0:
                drops.append((-delta, old_pos, new_pos, row))

        climbs.sort(key=lambda item: (-item[0], item[2]))
        if climbs:
            delta, old_pos, new_pos, row = climbs[0]
            name = _safe_team(row["team"])
            emoji = top5._club_emoji(guild, row["team"])
            lines.append(
                f"📈 {emoji} **{name}** fue el que más trepó: pasó del "
                f"**{_ordinal(old_pos)}** al **{_ordinal(new_pos)}** "
                f"({delta} puesto{'s' if delta != 1 else ''})."
            )
        elif drops:
            delta, old_pos, new_pos, row = sorted(
                drops, key=lambda item: (-item[0], item[2])
            )[0]
            name = _safe_team(row["team"])
            emoji = top5._club_emoji(guild, row["team"])
            lines.append(
                f"📉 {emoji} **{name}** sufrió el movimiento más fuerte: cayó del "
                f"**{_ordinal(old_pos)}** al **{_ordinal(new_pos)}**."
            )
        else:
            lines.append(
                f"🔒 No hubo cambios de posiciones: {leader_badge} **{leader_name}** "
                "sigue mandando."
            )

    if runner is not None:
        runner_name = _safe_team(runner["team"])
        runner_badge = top5._club_emoji(guild, runner["team"])
        gap = int(leader["pts"]) - int(runner["pts"])
        if gap > 0:
            lines.append(
                f"👑 La punta: {leader_badge} **{leader_name}** tiene **{leader['pts']} pts**, "
                f"**{gap}** por encima de {runner_badge} **{runner_name}**."
            )
        else:
            lines.append(
                f"⚖️ Arriba están igualados en **{leader['pts']} pts**: "
                f"{leader_badge} **{leader_name}** aparece por delante de "
                f"{runner_badge} **{runner_name}** por los criterios de desempate."
            )

    lines.extend(["", "👇 **Así quedó la tabla completa después de actualizar GES.**"])
    return "\n".join(lines)


def _font(ImageFont, size: int, bold: bool = False):
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
    value = str(text or "")
    if draw.textbbox((0, 0), value, font=font)[2] <= max_width:
        return value
    while len(value) > 3:
        value = value[:-1]
        candidate = value.rstrip() + "…"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            return candidate
    return value


_APP_BADGE_KEYS = {
    "ajax": ("team_badge_hq256", "ajax.png"),
    "asmonaco": ("team_badge_test", "as_monaco_hd.png"),
    "monaco": ("team_badge_test", "as_monaco_hd.png"),
    "astonvilla": ("team_badge_hq256", "aston_villa.png"),
    "atleticomadrid": ("team_badge_hq256", "atletico_madrid.png"),
    "atleticodemadrid": ("team_badge_hq256", "atletico_madrid.png"),
    "benfica": ("team_badge_hq256", "benfica.png"),
    "boltonwanderers": ("team_badge_hq256", "bolton_wanderers.png"),
    "bolton": ("team_badge_hq256", "bolton_wanderers.png"),
    "everton": ("team_badge_hq256", "everton.png"),
    "feyenoord": ("team_badge_hq256", "feyenoord.png"),
    "fiorentina": ("team_badge_hq256", "fiorentina.png"),
    "fulham": ("team_badge_hq256", "fulham.png"),
    "galatasaray": ("team_badge_hq256", "galatasaray.png"),
    "lazio": ("team_badge_hq256", "lazio.png"),
    "manchestercity": ("team_badge_hq256", "manchester_city.png"),
    "middlesbrough": ("team_badge_hq256", "middlesbrough.png"),
    "olympiquelyon": ("team_badge_hq256", "olympique_lyon.png"),
    "olympiquedelyon": ("team_badge_hq256", "olympique_lyon.png"),
    "lyon": ("team_badge_hq256", "olympique_lyon.png"),
    "olympiquemarseille": ("team_badge_hq256", "olympique_marseille.png"),
    "olympiquedemarseille": ("team_badge_hq256", "olympique_marseille.png"),
    "olympiquedemarsella": ("team_badge_hq256", "olympique_marseille.png"),
    "marsella": ("team_badge_hq256", "olympique_marseille.png"),
    "marseille": ("team_badge_hq256", "olympique_marseille.png"),
    "porto": ("team_badge_hq256", "porto.png"),
    "fcporto": ("team_badge_hq256", "porto.png"),
    "psg": ("team_badge_hq256", "psg.png"),
    "parissaintgermain": ("team_badge_hq256", "psg.png"),
    "parissaintgermainpsg": ("team_badge_hq256", "psg.png"),
    "realbetis": ("team_badge_hq256", "real_betis.png"),
    "betis": ("team_badge_hq256", "real_betis.png"),
    "sevilla": ("team_badge_hq256", "sevilla.png"),
    "sevillafc": ("team_badge_hq256", "sevilla.png"),
    "tottenhamhotspur": ("team_badge_hq256", "tottenham_hotspur.png"),
    "tottenham": ("team_badge_hq256", "tottenham_hotspur.png"),
    "villarreal": ("team_badge_hq256", "villarreal.png"),
    "villarrealcf": ("team_badge_hq256", "villarreal.png"),
    "westhamunited": ("team_badge_hq256", "west_ham_united.png"),
    "westham": ("team_badge_hq256", "west_ham_united.png"),
    "zaragoza": ("team_badge_hq256", "zaragoza.png"),
    "realzaragoza": ("team_badge_hq256", "zaragoza.png"),
}


# Exact border/accent colors used by mobile/src/TeamCardTheme.tsx.
_APP_TEAM_THEMES = (
    (re.compile(r"monaco"), "#d8b753"),
    (re.compile(r"ajax"), "#eeeeee"),
    (re.compile(r"atletico"), "#d7b75c"),
    (re.compile(r"aston.*villa"), "#85c9ec"),
    (re.compile(r"benfica"), "#d8b753"),
    (re.compile(r"bolton"), "#679cd7"),
    (re.compile(r"everton"), "#aac9ee"),
    (re.compile(r"feyenoord"), "#eeeeee"),
    (re.compile(r"fiorentina"), "#c1a0e5"),
    (re.compile(r"fulham"), "#b92d3c"),
    (re.compile(r"galatasaray"), "#f4b236"),
    (re.compile(r"lazio"), "#daeef4"),
    (re.compile(r"manchester.*city"), "#cee8f4"),
    (re.compile(r"middlesbrough"), "#eeeeee"),
    (re.compile(r"lyon"), "#db4053"),
    (re.compile(r"marseille|marsella"), "#c5e5f4"),
    (re.compile(r"porto"), "#d2e3ff"),
    (re.compile(r"psg|paris"), "#d83b52"),
    (re.compile(r"betis"), "#e0eee6"),
    (re.compile(r"sevilla"), "#eeeeee"),
    (re.compile(r"torino"), "#d5b876"),
    (re.compile(r"tottenham"), "#dce5ef"),
    (re.compile(r"villarreal"), "#e8d878"),
    (re.compile(r"west.*ham"), "#83badb"),
    (re.compile(r"zaragoza"), "#d5b65a"),
)


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = str(value or "").lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _app_team_border(team: str) -> tuple[int, int, int]:
    key = str(team or "").casefold()
    try:
        import unicodedata
        key = unicodedata.normalize("NFD", key)
        key = "".join(ch for ch in key if not unicodedata.combining(ch))
    except Exception:
        pass
    for pattern, color in _APP_TEAM_THEMES:
        if pattern.search(key):
            return _hex_rgb(color)
    return _hex_rgb("#71c4ff")


def _app_badge_path(team: str) -> str | None:
    key = top5._norm(team)
    info = _APP_BADGE_KEYS.get(key)
    if info:
        folder, filename = info
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "mobile",
            "assets",
            folder,
            filename,
        )
        if os.path.isfile(path):
            return path
    # Zaragoza's mobile source currently uses a remote image because its old APK
    # asset was problematic; keep the local Radio fallback if the HQ file is absent.
    return top5._asset_path(team)


def _clean_manager_name(member, club: str) -> str:
    if member is None:
        return ""
    for raw in (
        getattr(member, "global_name", None),
        getattr(member, "name", None),
        getattr(member, "display_name", None),
    ):
        value = str(raw or "").strip()
        if not value:
            continue
        suffix = f" | {club}".casefold()
        if value.casefold().endswith(suffix):
            value = value[: -len(suffix)].strip()
        if value:
            return value
    return ""


def _manager_names(guild) -> dict[str, str]:
    """Use the same live club assignment source that the mobile table relies on."""
    result: dict[str, str] = {}
    cached: dict[str, tuple[int | None, str]] = {}
    try:
        import mobile_write_api

        with mobile_write_api.write_db() as conn:
            if _table_exists(conn, "mobile_manager_names"):
                rows = conn.execute(
                    "SELECT club,user_id,manager_name FROM mobile_manager_names"
                ).fetchall()
                for row in rows:
                    key = top5._team_key(str(row["club"] or ""))
                    if not key:
                        continue
                    cached[key] = (
                        int(row["user_id"]) if row["user_id"] is not None else None,
                        str(row["manager_name"] or "").strip(),
                    )

            if not _table_exists(conn, "clubs"):
                return {key: name for key, (_, name) in cached.items() if name}

            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(clubs)").fetchall()
            }
            if not {"name", "user_id"}.issubset(columns):
                return {key: name for key, (_, name) in cached.items() if name}

            rows = conn.execute(
                """SELECT name,user_id FROM clubs
                   WHERE TRIM(COALESCE(name,''))<>''
                   ORDER BY name COLLATE NOCASE"""
            ).fetchall()
            for row in rows:
                club = str(row["name"] or "").strip()
                key = top5._team_key(club)
                if not key:
                    continue
                user_id = int(row["user_id"]) if row["user_id"] is not None else None
                manager_name = ""
                if user_id is not None and guild is not None:
                    manager_name = _clean_manager_name(guild.get_member(user_id), club)
                old_user_id, old_name = cached.get(key, (None, ""))
                if not manager_name and user_id is not None and old_user_id == user_id:
                    manager_name = old_name
                if manager_name:
                    result[key] = manager_name
    except Exception as exc:
        print(f"AJPA GES Tabla Radio: no se pudieron leer DTs de Mobile: {exc}")
        result = {key: name for key, (_, name) in cached.items() if name}
    return result


def _zone(index: int) -> tuple[str, tuple[int, int, int]]:
    # Keep this byte-for-byte equivalent in meaning to
    # mobile/scripts/apply-league-qualification-zones.mjs:
    # positions 1-16 Champions League, 17-24 Europa League.
    if index <= 15:
        if index == 0:
            return "Campeón + Champions League", _hex_rgb("#f2c94c")
        return "Champions League", _hex_rgb("#66a7ff")
    if index <= 23:
        return "Europa League", _hex_rgb("#e2a45c")
    return "", _hex_rgb("#718596")


def _render_table(
    rows: list[dict[str, Any]],
    competition_label: str,
    managers: dict[str, str] | None = None,
) -> io.BytesIO:
    """Render the Discord image from the exact current AJPA Mobile table tokens."""
    from PIL import Image, ImageDraw, ImageFont

    managers = managers or {}

    # Mobile table geometry is 524 logical px. Render at 2x so Discord keeps the
    # same proportions but text and badges stay crisp on phones.
    scale = 2
    table_width = 524 * scale
    content_pad = 16 * scale
    heading_h = 30 * scale
    hint_h = 22 * scale
    header_h = 34 * scale
    row_h = 50 * scale
    bottom_pad = 16 * scale
    width = table_width + content_pad * 2
    shell_y = heading_h + content_pad
    shell_h = hint_h + header_h + len(rows) * row_h
    height = shell_y + shell_h + bottom_pad

    image = Image.new("RGB", (width, height), _hex_rgb("#02060a"))
    draw = ImageDraw.Draw(image)

    # Same title token as s.listHeading.
    list_font = _font(ImageFont, 10 * scale, True)
    draw.text(
        (content_pad, 8 * scale),
        "🏆 TABLA DE POSICIONES",
        font=list_font,
        fill=_hex_rgb("#8ac5ff"),
    )

    shell_x = content_pad
    shell_right = shell_x + table_width - 1
    shell_bottom = shell_y + shell_h - 1
    draw.rounded_rectangle(
        (shell_x, shell_y, shell_right, shell_bottom),
        radius=14 * scale,
        fill=_hex_rgb("#050d15"),
        outline=_hex_rgb("#263b4d"),
        width=1 * scale,
    )

    # App's horizontal-scroll hint remains part of the table visual language.
    hint_font = _font(ImageFont, 9 * scale, True)
    draw.text(
        (shell_x + 10 * scale, shell_y + 6 * scale),
        "Deslizá ↔ para ver todas las estadísticas",
        font=hint_font,
        fill=_hex_rgb("#718596"),
    )

    table_top = shell_y + hint_h
    header_bottom = table_top + header_h
    draw.rectangle(
        (shell_x, table_top, shell_right, header_bottom),
        fill=_hex_rgb("#0d1d2a"),
    )
    draw.line(
        (shell_x, table_top, shell_right, table_top),
        fill=_hex_rgb("#1d3447"),
        width=scale,
    )
    draw.line(
        (shell_x, header_bottom, shell_right, header_bottom),
        fill=_hex_rgb("#31495c"),
        width=scale,
    )

    widths = [
        34 * scale,   # #
        170 * scale,  # EQUIPO
        38 * scale,   # PJ
        38 * scale,   # PG
        38 * scale,   # PE
        38 * scale,   # PP
        38 * scale,   # GF
        38 * scale,   # GC
        44 * scale,   # DG
        48 * scale,   # PTS
    ]
    labels = ["#", "EQUIPO", "PJ", "PG", "PE", "PP", "GF", "GC", "DG", "PTS"]
    starts = []
    cursor = shell_x
    for value in widths:
        starts.append(cursor)
        cursor += value

    header_font = _font(ImageFont, 9 * scale, True)
    for idx, (x, col_w, label) in enumerate(zip(starts, widths, labels)):
        if idx == 1:
            draw.text(
                (x + 8 * scale, table_top + 10 * scale),
                label,
                font=header_font,
                fill=_hex_rgb("#8fa6b8"),
            )
        else:
            box = draw.textbbox((0, 0), label, font=header_font)
            tw = box[2] - box[0]
            th = box[3] - box[1]
            draw.text(
                (x + (col_w - tw) / 2, table_top + (header_h - th) / 2 - 1 * scale),
                label,
                font=header_font,
                fill=_hex_rgb("#8fa6b8"),
            )

    pos_font = _font(ImageFont, 11 * scale, True)
    team_font = _font(ImageFont, 11 * scale, True)
    manager_font = _font(ImageFont, 8 * scale, True)
    zone_font = _font(ImageFont, 7 * scale, True)
    stat_font = _font(ImageFont, 11 * scale, True)
    points_font = _font(ImageFont, 12 * scale, True)

    for index, row in enumerate(rows):
        y = header_bottom + index * row_h
        row_bottom = y + row_h
        bg = "#08121c" if index % 2 == 0 else "#0c1925"
        draw.rectangle(
            (shell_x, y, shell_right, row_bottom),
            fill=_hex_rgb(bg),
        )

        border = _app_team_border(str(row.get("team") or ""))
        draw.rectangle(
            (shell_x, y, shell_x + 3 * scale - 1, row_bottom),
            fill=border,
        )
        draw.line(
            (shell_x, row_bottom - 1, shell_right, row_bottom - 1),
            fill=_hex_rgb("#182c3b"),
            width=scale,
        )

        pos = str(int(row.get("position") or index + 1))
        pbox = draw.textbbox((0, 0), pos, font=pos_font)
        draw.text(
            (
                starts[0] + (widths[0] - (pbox[2] - pbox[0])) / 2,
                y + (row_h - (pbox[3] - pbox[1])) / 2 - 1 * scale,
            ),
            pos,
            font=pos_font,
            fill=_hex_rgb("#f7fbff"),
        )

        team = str(row.get("team") or "")
        badge_size = 26 * scale
        badge_x = starts[1] + 8 * scale
        badge_y = y + (row_h - badge_size) // 2
        badge_path = _app_badge_path(team)
        if badge_path:
            try:
                badge = Image.open(badge_path).convert("RGBA")
                badge.thumbnail((badge_size, badge_size), Image.Resampling.LANCZOS)
                bx = badge_x + (badge_size - badge.width) // 2
                by = badge_y + (badge_size - badge.height) // 2
                # Mobile ClubBadge restores Ajax's white circular field.
                if top5._norm(team) == "ajax":
                    inset_x = int(badge_size * 0.115)
                    inset_y = int(badge_size * 0.22)
                    disc_w = int(badge_size * 0.77)
                    draw.ellipse(
                        (
                            badge_x + inset_x,
                            badge_y + inset_y,
                            badge_x + inset_x + disc_w,
                            badge_y + inset_y + disc_w,
                        ),
                        fill=(255, 255, 255),
                    )
                image.paste(badge, (bx, by), badge)
            except Exception:
                pass

        text_x = starts[1] + 8 * scale + badge_size + 8 * scale
        text_w = widths[1] - (text_x - starts[1]) - 6 * scale
        manager = managers.get(top5._team_key(team), "")
        zone_label, zone_color = _zone(index)

        team_text = _fit_text(draw, team, team_font, text_w)
        draw.text(
            (text_x, y + 5 * scale),
            team_text,
            font=team_font,
            fill=_hex_rgb("#f7fbff"),
        )

        manager_text = "DT: " + (manager or "Sin asignar")
        manager_text = _fit_text(draw, manager_text, manager_font, text_w)
        draw.text(
            (text_x, y + 19 * scale),
            manager_text,
            font=manager_font,
            fill=_hex_rgb("#a7b7c5"),
        )

        if zone_label:
            zone_y = y + 32 * scale
            dot = 5 * scale
            draw.ellipse(
                (text_x, zone_y + 1 * scale, text_x + dot, zone_y + 1 * scale + dot),
                fill=zone_color,
            )
            zone_text = _fit_text(
                draw,
                zone_label,
                zone_font,
                max(20, text_w - dot - 4 * scale),
            )
            draw.text(
                (text_x + dot + 4 * scale, zone_y),
                zone_text,
                font=zone_font,
                fill=zone_color,
            )

        values = [
            int(row.get("pj") or 0),
            int(row.get("pg") or 0),
            int(row.get("pe") or 0),
            int(row.get("pp") or 0),
            int(row.get("gf") or 0),
            int(row.get("gc") or 0),
        ]
        for col_idx, value in enumerate(values, start=2):
            label = str(value)
            box = draw.textbbox((0, 0), label, font=stat_font)
            draw.text(
                (
                    starts[col_idx] + (widths[col_idx] - (box[2] - box[0])) / 2,
                    y + (row_h - (box[3] - box[1])) / 2 - 1 * scale,
                ),
                label,
                font=stat_font,
                fill=_hex_rgb("#d6e1e9"),
            )

        dg = int(row.get("dg") or 0)
        dg_label = f"+{dg}" if dg > 0 else str(dg)
        box = draw.textbbox((0, 0), dg_label, font=stat_font)
        draw.text(
            (
                starts[8] + (widths[8] - (box[2] - box[0])) / 2,
                y + (row_h - (box[3] - box[1])) / 2 - 1 * scale,
            ),
            dg_label,
            font=stat_font,
            fill=_hex_rgb("#d6e1e9"),
        )

        pts_label = str(int(row.get("pts") or 0))
        box = draw.textbbox((0, 0), pts_label, font=points_font)
        draw.text(
            (
                starts[9] + (widths[9] - (box[2] - box[0])) / 2,
                y + (row_h - (box[3] - box[1])) / 2 - 1 * scale,
            ),
            pts_label,
            font=points_font,
            fill=border,
        )

    payload = io.BytesIO()
    image.save(payload, format="PNG", optimize=True)
    payload.seek(0)
    return payload

async def _publish_event(runtime, bot, guild, sync_run_id: int) -> bool:
    row = _event(runtime, int(guild.id), int(sync_run_id))
    if not row:
        return False
    if str(row["status"] or "").casefold() == "posted":
        return True

    channel = await top5._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(
            f"AJPA GES Tabla Radio pendiente sync={sync_run_id}: Radio Pasillo no encontrado"
        )
        return False

    try:
        before = json.loads(str(row["before_json"] or "[]"))
        after = json.loads(str(row["after_json"] or "[]"))
    except Exception as exc:
        print(f"AJPA GES Tabla Radio payload inválido sync={sync_run_id}: {exc}")
        return False

    if not after:
        return False

    managers = _manager_names(guild)
    image = _render_table(
        after,
        str(row["competition_label"] or "AJPA"),
        managers,
    )
    file = discord.File(image, filename=f"ajpa-tabla-app-{int(sync_run_id)}.png")
    try:
        sent = await channel.send(
            content=_commentary(guild, before, after),
            file=file,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"AJPA GES Tabla Radio envío falló sync={sync_run_id} "
            f"canal={getattr(channel, 'id', None)}: {type(exc).__name__}: {exc}"
        )
        return False

    _mark_posted(runtime, guild.id, int(sync_run_id), channel.id, sent.id)
    print(
        f"AJPA GES Tabla Radio publicado sync={sync_run_id} "
        f"guild={guild.id} channel={channel.id} equipos={len(after)}"
    )
    return True


async def _publish_pending(runtime, bot, guild) -> None:
    conn = ges.league.db(runtime, int(guild.id))
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            f"""SELECT sync_run_id FROM {_EVENT_TABLE}
                WHERE guild_id=? AND status='pending'
                ORDER BY sync_run_id ASC LIMIT 25""",
            (int(guild.id),),
        ).fetchall()
        ids = [int(row["sync_run_id"]) for row in rows]
    finally:
        conn.close()

    for sync_run_id in ids:
        try:
            await _publish_event(runtime, bot, guild, sync_run_id)
        except Exception as exc:
            print(
                f"AJPA GES Tabla Radio retry falló guild={guild.id} "
                f"sync={sync_run_id}: {type(exc).__name__}: {exc}"
            )


def _install_sync_wrapper(runtime, bot) -> None:
    base_sync = ges.sync_from_ges
    if getattr(base_sync, "_ajpa_ges_table_radio", False):
        return

    async def sync_with_table_radio(
        runtime_arg,
        bot_arg,
        guild_id: int,
        staff_user_id: int | None = None,
    ) -> dict:
        before_league_id = str(getattr(ges, "GES_LEAGUE_ID", "") or "")
        try:
            before = _standings(runtime_arg, int(guild_id), before_league_id)
        except Exception as exc:
            print(
                f"AJPA GES Tabla Radio snapshot previo falló guild={guild_id}: "
                f"{type(exc).__name__}: {exc}"
            )
            before = []

        result = await base_sync(
            runtime_arg,
            bot_arg,
            int(guild_id),
            staff_user_id,
        )
        if not result or not result.get("ok"):
            return result

        league_id = str(result.get("league_id") or getattr(ges, "GES_LEAGUE_ID", "") or "")
        if before_league_id and league_id and before_league_id != league_id:
            before = []

        try:
            after = _standings(runtime_arg, int(guild_id), league_id)
            sync_run_id = _latest_sync_run_id(runtime_arg, int(guild_id), league_id)
            if after and sync_run_id is not None:
                _store_event(
                    runtime_arg,
                    int(guild_id),
                    int(sync_run_id),
                    league_id,
                    str(result.get("competition_label") or "Liga AJPA"),
                    before,
                    after,
                )
                guild = bot_arg.get_guild(int(guild_id))
                if guild is not None:
                    try:
                        await _publish_event(
                            runtime_arg,
                            bot_arg,
                            guild,
                            int(sync_run_id),
                        )
                    except Exception as exc:
                        print(
                            f"AJPA GES Tabla Radio post-sync falló guild={guild_id} "
                            f"sync={sync_run_id}: {type(exc).__name__}: {exc}"
                        )
        except Exception as exc:
            # A Radio Pasillo problem must never invalidate a successful official
            # GES synchronization. The competitive snapshot is already committed.
            print(
                f"AJPA GES Tabla Radio no pudo preparar publicación guild={guild_id}: "
                f"{type(exc).__name__}: {exc}"
            )
        return result

    sync_with_table_radio._ajpa_ges_table_radio = True
    sync_with_table_radio._ajpa_ges_table_radio_base = base_sync
    ges.sync_from_ges = sync_with_table_radio


def _patch_seasonal_reinstall() -> None:
    current = seasonal.apply_season_ges_authority
    if getattr(current, "_ajpa_ges_table_radio_reinstall", False):
        return

    def apply_season_with_table_radio(runtime, bot):
        current(runtime, bot)
        _install_sync_wrapper(runtime, bot)

    apply_season_with_table_radio._ajpa_ges_table_radio_reinstall = True
    seasonal.apply_season_ges_authority = apply_season_with_table_radio


def apply_ges_table_radio(runtime, bot) -> None:
    _install_sync_wrapper(runtime, bot)
    _patch_seasonal_reinstall()

    if getattr(runtime, "_ajpa_ges_table_radio_ready", False):
        return

    async def ready_listener():
        for guild in list(getattr(bot, "guilds", []) or []):
            try:
                await _publish_pending(runtime, bot, guild)
            except Exception as exc:
                print(
                    f"AJPA GES Tabla Radio recuperación guild={getattr(guild, 'id', None)}: "
                    f"{type(exc).__name__}: {exc}"
                )

    bot.add_listener(ready_listener, "on_ready")
    runtime._ajpa_ges_table_radio_ready = True
    print(
        "AJPA Radio Pasillo: tabla completa se publica después de cada 'GES actualizada'"
    )


_BASE_APPLY_GUILD = guild_isolation.apply_guild_isolation_patch


def _apply_guild_then_ges_table_radio(runtime, bot):
    _BASE_APPLY_GUILD(runtime, bot)
    apply_ges_table_radio(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_ges_table_radio_wrapped",
    False,
):
    _apply_guild_then_ges_table_radio._ajpa_ges_table_radio_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_then_ges_table_radio
