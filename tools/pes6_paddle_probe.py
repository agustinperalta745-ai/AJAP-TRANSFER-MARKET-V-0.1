"""Isolated PES6 OCR experiment using PaddleOCR.

This file is intentionally NOT imported by the production bot.  It exists only
on the experiment/paddleocr-pes6 branch so we can benchmark real AJAP captures
without touching league data or Discord result handling.

Usage:
    python tools/pes6_paddle_probe.py /path/to/capture.png

The script crops the known PES6 result regions first and asks PaddleOCR to read
only those small areas.  That keeps the test deterministic and much cheaper than
running OCR over a full phone screenshot.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps


# Coordinates are relative to the normalized PES6 frame after phone letterbox
# removal.  They deliberately overlap a little so normal capture scaling does not
# move important glyphs outside the crop.
REGIONS = {
    "home_team": (0.00, 0.06, 0.53, 0.23),
    "away_team": (0.47, 0.06, 1.00, 0.23),
    "home_score": (0.265, 0.20, 0.405, 0.42),
    "away_score": (0.595, 0.20, 0.735, 0.42),
    "final_state": (0.18, 0.10, 0.82, 0.72),
    "scorer_left": (0.00, 0.18, 0.50, 0.82),
    "scorer_right": (0.50, 0.18, 1.00, 0.82),
}

FINAL_MARKERS = (
    "resultado",
    "terminar juego",
    "jugar otro partido",
    "detalles del partido",
    "2do",
    "2nd",
    "result",
    "match details",
    "exit match series",
)


def _crop_phone_letterbox(image: Image.Image) -> Image.Image:
    """Reuse the production crop when available; keep this probe standalone."""
    try:
        from league_phone_screenshot_crop_patch import _crop_phone_letterbox as crop
        return crop(image)
    except Exception:
        return image


def _crop(image: Image.Image, frac) -> Image.Image:
    x0, y0, x1, y1 = frac
    w, h = image.size
    return image.crop((
        max(0, int(w * x0)),
        max(0, int(h * y0)),
        min(w, max(1, int(w * x1))),
        min(h, max(1, int(h * y1))),
    ))


def _prepare(crop: Image.Image, *, digit: bool = False) -> Image.Image:
    # Upscale only the small PES region.  This is the key difference from the
    # current full-frame OCR path.
    scale = 6 if digit else 3
    target = crop.resize(
        (max(1, crop.width * scale), max(1, crop.height * scale)),
        Image.Resampling.BICUBIC if digit else Image.Resampling.LANCZOS,
    )
    if digit:
        gray = ImageOps.grayscale(target)
        gray = ImageOps.autocontrast(gray)
        gray = ImageEnhance.Contrast(gray).enhance(1.6)
        return gray.convert("RGB")
    return ImageOps.autocontrast(target.convert("RGB"))


def _result_payload(res):
    """PaddleOCR result objects changed shape across 3.x; normalize defensively."""
    candidates = []
    try:
        candidates.append(res.json)
    except Exception:
        pass
    try:
        candidates.append(dict(res))
    except Exception:
        pass
    candidates.append(res)

    for candidate in candidates:
        if callable(candidate):
            try:
                candidate = candidate()
            except Exception:
                continue
        if isinstance(candidate, dict):
            inner = candidate.get("res") if isinstance(candidate.get("res"), dict) else candidate
            texts = inner.get("rec_texts")
            scores = inner.get("rec_scores")
            if texts is not None:
                try:
                    texts = [str(x).strip() for x in list(texts)]
                except Exception:
                    texts = []
                try:
                    scores = [float(x) for x in list(scores)] if scores is not None else []
                except Exception:
                    scores = []
                return texts, scores
            text = inner.get("rec_text")
            if text:
                score = inner.get("rec_score")
                return [str(text).strip()], [float(score or 0.0)]
    return [], []


def _read_region(ocr, crop: Image.Image, label: str) -> dict:
    # File input is intentionally used here because it is part of PaddleOCR's
    # documented public API and avoids depending on undocumented ndarray shapes.
    with tempfile.TemporaryDirectory(prefix="ajap_paddle_") as tmp:
        path = Path(tmp) / f"{label}.png"
        crop.save(path)
        texts: list[str] = []
        scores: list[float] = []
        for res in ocr.predict(str(path)):
            t, s = _result_payload(res)
            texts.extend(t)
            scores.extend(s)
    return {
        "texts": [x for x in texts if x],
        "scores": scores,
        "text": " | ".join(x for x in texts if x),
    }


def _parse_digit(text: str):
    # Score crops contain one large glyph.  Accept only a single plausible
    # integer; never infer a value from arbitrary neighbouring menu text.
    nums = re.findall(r"(?<!\d)(\d{1,2})(?!\d)", str(text or ""))
    vals = [int(x) for x in nums if 0 <= int(x) <= 20]
    if len(vals) == 1:
        return vals[0]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="AJAP isolated PaddleOCR PES6 probe")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()

    from paddleocr import PaddleOCR

    image = Image.open(args.image).convert("RGB")
    frame = _crop_phone_letterbox(image)

    # Official PaddleOCR 3.x local pipeline.  No hosted API/token is used.
    ocr = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        engine="paddle",
        device="cpu",
    )

    reads = {}
    for name, frac in REGIONS.items():
        prepared = _prepare(_crop(frame, frac), digit=name.endswith("_score"))
        reads[name] = _read_region(ocr, prepared, name)

    state_key = reads["final_state"]["text"].casefold()
    payload = {
        "source": str(args.image),
        "original_size": list(image.size),
        "normalized_size": list(frame.size),
        "home_team_raw": reads["home_team"]["text"],
        "away_team_raw": reads["away_team"]["text"],
        "home_goals": _parse_digit(reads["home_score"]["text"]),
        "away_goals": _parse_digit(reads["away_score"]["text"]),
        "is_final": any(marker in state_key for marker in FINAL_MARKERS),
        "state_raw": reads["final_state"]["text"],
        "scorer_left_raw": reads["scorer_left"]["texts"],
        "scorer_right_raw": reads["scorer_right"]["texts"],
        "reads": reads,
    }
    payload["result_complete"] = bool(
        payload["home_team_raw"]
        and payload["away_team_raw"]
        and payload["home_goals"] is not None
        and payload["away_goals"] is not None
        and payload["is_final"]
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["result_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
