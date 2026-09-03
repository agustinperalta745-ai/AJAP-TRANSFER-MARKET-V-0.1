"""Normalize tall phone screenshots before AJAP local OCR.

PES6 screenshots are often uploaded as full Android screenshots with very large
black bars above/below the game image. The local OCR previously normalized all
coordinates against the whole phone canvas, which made the PES username panel
fall outside the expected top area and left the actual game UI too small for a
reliable score/team read.

This patch finds the dense horizontal content band, crops only when the source
clearly looks letterboxed, then runs the same RapidOCR engine on the normalized
PES image. Ordinary screenshots are left untouched.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

import league_local_ocr_patch as local


_BASE_OCR_ONE = local._ocr_one


def _merge_regions(indices, max_gap: int):
    if len(indices) == 0:
        return []
    regions = []
    start = prev = int(indices[0])
    for raw in indices[1:]:
        value = int(raw)
        if value - prev > max_gap:
            regions.append((start, prev))
            start = value
        prev = value
    regions.append((start, prev))
    return regions


def _crop_phone_letterbox(image: Image.Image) -> Image.Image:
    """Crop large black phone bars while preserving the complete PES6 frame."""
    if image.height < 500 or image.width < 300:
        return image

    arr = np.asarray(image.convert("RGB"))
    # A row is considered real image content when a meaningful fraction of its
    # pixels are visibly above black. Android navigation glyphs alone are too
    # sparse to pass this threshold.
    visible = np.max(arr, axis=2) > 22
    row_activity = visible.mean(axis=1)
    active = np.where(row_activity >= 0.16)[0]
    if len(active) == 0:
        return image

    max_gap = max(10, int(image.height * 0.025))
    regions = _merge_regions(active, max_gap=max_gap)
    if not regions:
        return image

    # Prefer the largest dense band. This selects the PES6 frame instead of a
    # notification/status strip or the Android navigation buttons.
    def region_score(region):
        top, bottom = region
        height = bottom - top + 1
        density = float(row_activity[top : bottom + 1].mean())
        return height * (0.55 + density)

    top, bottom = max(regions, key=region_score)
    band_h = bottom - top + 1

    # Only crop when it is unmistakably letterboxed. Never trim a normal game
    # capture merely because a few dark rows exist at an edge.
    if band_h < max(120, int(image.height * 0.14)):
        return image
    if band_h > int(image.height * 0.86):
        return image
    if top < int(image.height * 0.06) and bottom > int(image.height * 0.94):
        return image

    pad = max(8, int(band_h * 0.025))
    top = max(0, top - pad)
    bottom = min(image.height - 1, bottom + pad)
    cropped = image.crop((0, top, image.width, bottom + 1))

    # Do not accept pathological crops.
    if cropped.height < 120 or cropped.width < 300:
        return image
    return cropped


def _ocr_one_phone_safe(data: bytes):
    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
        image = _crop_phone_letterbox(image)
        image = ImageOps.autocontrast(image)
        image = ImageEnhance.Contrast(image).enhance(1.25)

        # Upscale the actual PES frame, not the full 1536px phone canvas. This is
        # the key reliability improvement for team names, score digits and PES ID.
        if image.width < 1000:
            scale = min(2.2, 1300.0 / max(1, image.width))
            image = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                Image.Resampling.LANCZOS,
            )

        arr = np.asarray(image)
        raw = local._engine()(arr)
        if isinstance(raw, tuple):
            raw = raw[0]

        items = []
        for row in raw or []:
            try:
                box, text, conf = row[0], str(row[1]).strip(), float(row[2])
            except Exception:
                continue
            if not text:
                continue
            x, y = local._box_center(box)
            items.append(
                {
                    "box": box,
                    "text": text,
                    "conf": conf,
                    "x": x,
                    "y": y,
                    "w": float(image.width),
                    "h": float(image.height),
                }
            )
        return items
    except Exception as exc:
        # Preserve the previous reader as a safe fallback for unusual formats.
        print(f"WARNING AJAP crop OCR: {type(exc).__name__}: {exc}; usando lector base")
        return _BASE_OCR_ONE(data)


local._ocr_one = _ocr_one_phone_safe

print("AJAP Liga: normalización de capturas verticales/letterbox activa")
