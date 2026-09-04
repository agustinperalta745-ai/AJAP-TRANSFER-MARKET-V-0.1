"""Corrige escudos/emojis del Top 5 de Radio Pasillo.

El Top 5 recibe nombres canónicos de Liga (por ejemplo ``Real Zaragoza`` y
``París Saint-Germain (PSG)``), mientras que los emojis manuales y algunos PNG
usan nombres más cortos. Además, varios PNG conservan margen transparente, lo
que hacía que el escudo quedara casi invisible al reducirlo a 66 px.

Esta capa conserva toda la lógica de adelantamientos y publicación; solamente
normaliza la resolución visual de clubes y recorta el margen transparente de
los PNG antes de que el renderizador los inserte en la tabla.
"""

from __future__ import annotations

import os
import re
import tempfile

from PIL import Image

import league_automation_patch as league
import league_top5_overtake_radio_patch as top5
import team_badge_selector_patch as selector


if not getattr(top5, "_ajap_top5_badge_fix_v2", False):
    # Nombres canónicos que no coincidían con las claves históricas del mapa.
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
    _CACHE_DIR = os.path.join(tempfile.gettempdir(), "ajpa_top5_badges_v2")

    # El selector del servidor usa estos nombres manuales para dos clubes cuyo
    # nombre oficial de Liga es distinto.
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

        # PSG llega desde Liga con "(PSG)"; el emoji manual está registrado sin
        # ese sufijo. Mantener también la versión sin paréntesis evita depender
        # de una lista frágil de aliases.
        without_parentheses = re.sub(r"\s*\([^)]*\)\s*", " ", raw).strip()
        if without_parentheses:
            candidates.append(without_parentheses)

        override = _MANUAL_NAME_OVERRIDES.get(top5._norm(raw))
        if override:
            candidates.append(override)

        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            marker = top5._norm(candidate)
            if marker and marker not in seen:
                seen.add(marker)
                unique.append(candidate)
        return unique

    def _club_emoji_fixed(guild, club: str) -> str:
        try:
            manual_clubs = list(getattr(selector, "MANUAL_EMOJI_NAMES", {}) or {})
            by_normalized = {top5._norm(name): name for name in manual_clubs}

            for candidate in _club_candidates(club):
                configured = by_normalized.get(top5._norm(candidate))
                if not configured:
                    continue
                emoji = selector._find_badge_emoji(guild, configured)
                if emoji is not None:
                    return str(emoji)
        except Exception:
            pass

        # Conserva todos los fallbacks anteriores si el servidor no tiene ese
        # emoji manual o Discord lo marca temporalmente como no disponible.
        return _ORIGINAL_CLUB_EMOJI(guild, club)

    def _trimmed_badge_path(path: str) -> str:
        try:
            stat = os.stat(path)
            os.makedirs(_CACHE_DIR, exist_ok=True)
            stem = os.path.splitext(os.path.basename(path))[0]
            cached = os.path.join(
                _CACHE_DIR,
                f"{stem}-{stat.st_size}-{stat.st_mtime_ns}.png",
            )
            if os.path.isfile(cached):
                return cached

            with Image.open(path) as source:
                badge = source.convert("RGBA")
                alpha = badge.getchannel("A")
                bbox = alpha.getbbox()
                if bbox:
                    badge = badge.crop(bbox)
                badge.save(cached, format="PNG", optimize=True)
            return cached
        except Exception as exc:
            print(
                "WARNING AJAP Top5: no se pudo normalizar escudo "
                f"path={path!r} error={type(exc).__name__}: {exc}"
            )
            return path

    def _asset_path_fixed(team: str) -> str | None:
        # La función original sigue siendo la autoridad para elegir el archivo;
        # este wrapper solo agrega aliases y corrige el canvas transparente.
        path = _ORIGINAL_ASSET_PATH(team)
        if not path:
            return None
        return _trimmed_badge_path(path)

    top5._club_emoji = _club_emoji_fixed
    top5._asset_path = _asset_path_fixed
    top5._ajap_top5_badge_fix_v2 = True

    print(
        "AJAP Radio Pasillo Top5: escudos/emojis normalizados "
        "(PSG/Zaragoza aliases + PNG sin margen transparente)"
    )
