"""Escudos correctos y consistentes para Radio Pasillo Top 5.

La tabla de Liga usa nombres canónicos que no siempre coinciden con el nombre
registrado para el emoji manual de Discord. Además, varios PNG locales históricos
tienen canvas/fondo distinto y se veían invisibles o con cuadrados negros.

Solución definitiva:
- el texto sigue usando el emoji manual real del servidor;
- antes de renderizar una publicación se descargan esos mismos emojis de Discord;
- la imagen Top 5 usa esos bytes como fuente principal y los compone en RGBA;
- los PNG locales quedan solo como fallback y se limpian de fondo conectado al borde.
"""

from __future__ import annotations

from collections import deque
from contextvars import ContextVar
import io
import json
import os
import re
import tempfile

from PIL import Image, ImageDraw

import league_automation_patch as league
import league_top5_overtake_radio_patch as top5
import team_badge_selector_patch as selector


if not getattr(top5, "_ajap_top5_badge_fix_v3", False):
    top5._BADGE_FILES.update(
        {
            "realzaragoza": "zaragoza.png",
            "parissaintgermainpsg": "psg.png",
            "atleticodemadrid": "atletico_madrid.png",
            "olympiquedelyon": "olympique_lyon.png",
            "olympiquedemarsella": "olympique_marseille.png",
        }
    )

    _ORIGINAL_CLUB_EMOJI = top5._club_emoji
    _ORIGINAL_ASSET_PATH = top5._asset_path
    _ORIGINAL_PUBLISH_EVENT = top5._publish_event
    _BADGE_CONTEXT: ContextVar[dict[str, bytes] | None] = ContextVar(
        "ajap_top5_badge_bytes", default=None
    )
    _CACHE_DIR = os.path.join(tempfile.gettempdir(), "ajpa_top5_badges_v3")

    _MANUAL_NAME_OVERRIDES = {
        top5._norm("Real Zaragoza"): "Zaragoza",
        top5._norm("París Saint-Germain (PSG)"): "Paris Saint-Germain",
    }

    def _club_candidates(club: str) -> list[str]:
        raw = str(club or "").strip()
        candidates = [raw]
        try:
            canonical = league.canonical_team(raw)
            if canonical:
                candidates.append(str(canonical))
        except Exception:
            pass

        without_parentheses = re.sub(r"\s*\([^)]*\)\s*", " ", raw).strip()
        if without_parentheses:
            candidates.append(without_parentheses)

        override = _MANUAL_NAME_OVERRIDES.get(top5._norm(raw))
        if override:
            candidates.append(override)

        result: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            marker = top5._norm(candidate)
            if marker and marker not in seen:
                seen.add(marker)
                result.append(candidate)
        return result

    def _manual_configured_club(club: str) -> str | None:
        manual = getattr(selector, "MANUAL_EMOJI_NAMES", {}) or {}
        by_norm = {top5._norm(name): name for name in manual}
        for candidate in _club_candidates(club):
            configured = by_norm.get(top5._norm(candidate))
            if configured:
                return configured
        return None

    def _manual_emoji(guild, club: str):
        if guild is None:
            return None
        configured = _manual_configured_club(club)
        if not configured:
            return None
        try:
            return selector._find_badge_emoji(guild, configured)
        except Exception:
            return None

    def _club_emoji_fixed(guild, club: str) -> str:
        emoji = _manual_emoji(guild, club)
        if emoji is not None:
            return str(emoji)
        return _ORIGINAL_CLUB_EMOJI(guild, club)

    def _trimmed_badge_path(path: str) -> str:
        try:
            stat = os.stat(path)
            os.makedirs(_CACHE_DIR, exist_ok=True)
            stem = os.path.splitext(os.path.basename(path))[0]
            cached = os.path.join(
                _CACHE_DIR, f"{stem}-{stat.st_size}-{stat.st_mtime_ns}.png"
            )
            if os.path.isfile(cached):
                return cached

            with Image.open(path) as source:
                badge = _prepare_badge(source)
                badge.save(cached, format="PNG", optimize=True)
            return cached
        except Exception as exc:
            print(
                "WARNING AJAP Top5: no se pudo normalizar PNG local "
                f"path={path!r} error={type(exc).__name__}: {exc}"
            )
            return path

    def _asset_path_fixed(team: str) -> str | None:
        path = _ORIGINAL_ASSET_PATH(team)
        return _trimmed_badge_path(path) if path else None

    def _similar(rgb, target, threshold: int = 38) -> bool:
        return sum((int(rgb[i]) - int(target[i])) ** 2 for i in range(3)) <= threshold**2

    def _remove_connected_border_background(image: Image.Image) -> Image.Image:
        """Quita solo un fondo uniforme conectado al borde; preserva el escudo interno."""
        img = image.convert("RGBA")
        w, h = img.size
        if w < 3 or h < 3:
            return img

        px = img.load()
        corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
        opaque = [c for c in corners if c[3] >= 220]
        if len(opaque) < 3:
            return img

        bg = tuple(sum(c[i] for c in opaque) // len(opaque) for i in range(3))
        if sum(1 for c in opaque if _similar(c, bg, 30)) < 3:
            return img

        queue: deque[tuple[int, int]] = deque()
        seen: set[tuple[int, int]] = set()
        for x in range(w):
            queue.append((x, 0))
            queue.append((x, h - 1))
        for y in range(h):
            queue.append((0, y))
            queue.append((w - 1, y))

        while queue:
            x, y = queue.popleft()
            if (x, y) in seen:
                continue
            seen.add((x, y))
            color = px[x, y]
            if color[3] < 16:
                continue
            if not _similar(color, bg):
                continue
            px[x, y] = (color[0], color[1], color[2], 0)
            if x > 0:
                queue.append((x - 1, y))
            if x + 1 < w:
                queue.append((x + 1, y))
            if y > 0:
                queue.append((x, y - 1))
            if y + 1 < h:
                queue.append((x, y + 1))
        return img

    def _prepare_badge(source) -> Image.Image:
        badge = source.convert("RGBA")
        badge = _remove_connected_border_background(badge)
        bbox = badge.getchannel("A").getbbox()
        if bbox:
            badge = badge.crop(bbox)
        return badge

    def _badge_image(team: str, payloads: dict[str, bytes] | None) -> Image.Image | None:
        key = top5._team_key(team)
        if payloads and payloads.get(key):
            try:
                with Image.open(io.BytesIO(payloads[key])) as source:
                    return _prepare_badge(source)
            except Exception as exc:
                print(
                    "WARNING AJAP Top5: emoji Discord inválido "
                    f"team={team!r} error={type(exc).__name__}: {exc}"
                )

        path = _asset_path_fixed(team)
        if not path:
            return None
        try:
            with Image.open(path) as source:
                return _prepare_badge(source)
        except Exception as exc:
            print(
                "WARNING AJAP Top5: PNG fallback inválido "
                f"team={team!r} path={path!r} error={type(exc).__name__}: {exc}"
            )
            return None

    def _render_top5_fixed(after: list[dict], payloads: dict[str, bytes] | None = None) -> io.BytesIO:
        width, height = 1200, 860
        image = Image.new("RGBA", (width, height), (13, 16, 24, 255))
        draw = ImageDraw.Draw(image)

        draw.rounded_rectangle((42, 38, width - 42, height - 38), radius=34, fill=(24, 29, 42, 255))
        draw.rounded_rectangle((42, 38, width - 42, 172), radius=34, fill=(35, 42, 59, 255))
        draw.rectangle((42, 138, width - 42, 172), fill=(35, 42, 59, 255))

        title_font = top5._font(52, bold=True)
        sub_font = top5._font(25)
        header_font = top5._font(23, bold=True)
        row_font = top5._font(30, bold=True)
        stat_font = top5._font(28, bold=True)
        pos_font = top5._font(34, bold=True)

        draw.text((82, 66), "LIGA", font=title_font, fill=(246, 248, 252, 255))
        draw.text((82, 126), "TOP 5 • TABLA ACTUALIZADA", font=sub_font, fill=(178, 187, 207, 255))

        y_header = 194
        for xy, label in [((84, y_header), "#"), ((215, y_header), "EQUIPO"), ((845, y_header), "PJ"), ((955, y_header), "DG"), ((1070, y_header), "PTS")]:
            draw.text(xy, label, font=header_font, fill=(152, 162, 184, 255))

        row_top = 238
        row_h = 112
        for idx, row in enumerate(after[:5], start=1):
            y = row_top + (idx - 1) * row_h
            fill = (30, 36, 51, 255) if idx % 2 else (27, 33, 47, 255)
            draw.rounded_rectangle((68, y, width - 68, y + 94), radius=22, fill=fill)

            pos = str(idx)
            pos_box = draw.textbbox((0, 0), pos, font=pos_font)
            pos_w = pos_box[2] - pos_box[0]
            draw.text((113 - pos_w / 2, y + 25), pos, font=pos_font, fill=(244, 246, 250, 255))

            badge = _badge_image(str(row["team"]), payloads)
            if badge is not None and badge.getchannel("A").getbbox():
                badge.thumbnail((66, 66), Image.Resampling.LANCZOS)
                tile = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
                tile.alpha_composite(badge, ((72 - badge.width) // 2, (72 - badge.height) // 2))
                image.alpha_composite(tile, (134, y + 11))

            name = top5._fit_text(draw, str(row["team"]), row_font, 540)
            draw.text((215, y + 28), name, font=row_font, fill=(246, 248, 252, 255))
            draw.text((850, y + 30), str(int(row["pj"])), font=stat_font, fill=(225, 229, 238, 255))
            dg = int(row["dg"])
            dg_text = f"+{dg}" if dg > 0 else str(dg)
            draw.text((947, y + 30), dg_text, font=stat_font, fill=(225, 229, 238, 255))
            draw.text((1070, y + 27), str(int(row["pts"])), font=pos_font, fill=(255, 255, 255, 255))

        draw.text((82, height - 82), "AJPA • Radio Pasillo", font=top5._font(21, bold=True), fill=(143, 153, 174, 255))

        payload = io.BytesIO()
        image.convert("RGB").save(payload, format="PNG", optimize=True)
        payload.seek(0)
        return payload

    async def _discord_badge_payloads(guild, rows) -> dict[str, bytes]:
        payloads: dict[str, bytes] = {}
        for row in list(rows)[:5]:
            team = str(row["team"])
            emoji = _manual_emoji(guild, team)
            if emoji is None:
                continue
            try:
                data = await emoji.read()
                if data:
                    payloads[top5._team_key(team)] = bytes(data)
            except Exception as exc:
                print(
                    "WARNING AJAP Top5: no se pudo leer emoji Discord "
                    f"team={team!r} emoji={getattr(emoji, 'name', None)!r} "
                    f"error={type(exc).__name__}: {exc}"
                )
        return payloads

    async def _render_top5_for_guild(guild, rows) -> io.BytesIO:
        payloads = await _discord_badge_payloads(guild, rows)
        return _render_top5_fixed(list(rows), payloads)

    def _render_top5_contextual(after) -> io.BytesIO:
        return _render_top5_fixed(list(after), _BADGE_CONTEXT.get())

    async def _publish_event_with_badges(runtime, bot, guild, source_message_id: int) -> bool:
        payloads: dict[str, bytes] = {}
        try:
            row = top5._event(runtime, guild.id, int(source_message_id))
            if row:
                after = json.loads(str(row["after_json"]))
                payloads = await _discord_badge_payloads(guild, after)
        except Exception as exc:
            print(
                f"WARNING AJAP Top5: precarga escudos falló mensaje={source_message_id}: "
                f"{type(exc).__name__}: {exc}"
            )

        token = _BADGE_CONTEXT.set(payloads)
        try:
            return await _ORIGINAL_PUBLISH_EVENT(runtime, bot, guild, int(source_message_id))
        finally:
            _BADGE_CONTEXT.reset(token)

    top5._club_emoji = _club_emoji_fixed
    top5._asset_path = _asset_path_fixed
    top5._render_top5 = _render_top5_contextual
    top5._render_top5_for_guild = _render_top5_for_guild
    top5._publish_event = _publish_event_with_badges
    top5._ajap_top5_badge_fix_v3 = True

    print(
        "AJAP Radio Pasillo Top5: v3 activo — la imagen usa los mismos emojis "
        "manuales de Discord con composición RGBA"
    )
