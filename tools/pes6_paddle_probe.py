"""Isolated PES6 OCR experiment using PaddleOCR.

This module is NOT imported by production. It reads fixed PES6 result regions and
prints JSON so AJAP can benchmark a free local reader before integrating it.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

REGIONS = {
    "home_team": (0.00, 0.06, 0.53, 0.23),
    "away_team": (0.47, 0.06, 1.00, 0.23),
    "home_score": (0.265, 0.20, 0.405, 0.42),
    "away_score": (0.595, 0.20, 0.735, 0.42),
    "final_state": (0.18, 0.10, 0.82, 0.72),
}

FINAL_MARKERS = (
    "resultado", "terminar juego", "jugar otro partido", "detalles del partido",
    "2do", "2nd", "result", "match details", "exit match series",
)


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
    """Standalone copy of AJAP's conservative phone/letterbox crop."""
    if image.height < 500 or image.width < 300:
        return image
    arr = np.asarray(image.convert("RGB"))
    visible = np.max(arr, axis=2) > 22
    row_activity = visible.mean(axis=1)
    active = np.where(row_activity >= 0.16)[0]
    if len(active) == 0:
        return image
    regions = _merge_regions(active, max_gap=max(10, int(image.height * 0.025)))
    if not regions:
        return image

    def region_score(region):
        top, bottom = region
        height = bottom - top + 1
        density = float(row_activity[top : bottom + 1].mean())
        return height * (0.55 + density)

    top, bottom = max(regions, key=region_score)
    band_h = bottom - top + 1
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
    return cropped if cropped.height >= 120 and cropped.width >= 300 else image


def _crop(image: Image.Image, frac) -> Image.Image:
    x0, y0, x1, y1 = frac
    w, h = image.size
    return image.crop((
        max(0, int(w * x0)), max(0, int(h * y0)),
        min(w, max(1, int(w * x1))), min(h, max(1, int(h * y1))),
    ))


def _prepare(crop: Image.Image, *, digit: bool = False) -> Image.Image:
    scale = 7 if digit else 3
    target = crop.resize(
        (max(1, crop.width * scale), max(1, crop.height * scale)),
        Image.Resampling.BICUBIC if digit else Image.Resampling.LANCZOS,
    )
    if digit:
        gray = ImageOps.autocontrast(ImageOps.grayscale(target))
        gray = ImageEnhance.Contrast(gray).enhance(1.45)
        return gray.convert("RGB")
    return ImageOps.autocontrast(target.convert("RGB"))


def _result_payload(res):
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
        if not isinstance(candidate, dict):
            continue
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
            try:
                score = float(inner.get("rec_score") or 0.0)
            except Exception:
                score = 0.0
            return [str(text).strip()], [score]
    return [], []


def _read_region(ocr, crop: Image.Image, label: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="ajap_paddle_") as tmp:
        path = Path(tmp) / f"{label}.png"
        crop.save(path)
        texts, scores = [], []
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
    nums = re.findall(r"(?<!\d)(\d{1,2})(?!\d)", str(text or ""))
    vals = [int(x) for x in nums if 0 <= int(x) <= 20]
    return vals[0] if len(vals) == 1 else None


def probe(image_path: Path) -> dict:
    from paddleocr import PaddleOCR

    image = Image.open(image_path).convert("RGB")
    frame = _crop_phone_letterbox(image)
    started = time.perf_counter()

    # Tiny PP-OCRv6 models are intentional here: this experiment is testing
    # whether AJAP can stay local/free on CPU, not maximum server-model accuracy.
    ocr = PaddleOCR(
        ocr_version="PP-OCRv6",
        text_detection_model_name="PP-OCRv6_tiny_det",
        text_recognition_model_name="PP-OCRv6_tiny_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device="cpu",
    )

    reads = {}
    for name, frac in REGIONS.items():
        reads[name] = _read_region(
            ocr,
            _prepare(_crop(frame, frac), digit=name.endswith("_score")),
            name,
        )

    state_key = reads["final_state"]["text"].casefold()
    out = {
        "source": str(image_path),
        "original_size": list(image.size),
        "normalized_size": list(frame.size),
        "home_team_raw": reads["home_team"]["text"],
        "away_team_raw": reads["away_team"]["text"],
        "home_goals": _parse_digit(reads["home_score"]["text"]),
        "away_goals": _parse_digit(reads["away_score"]["text"]),
        "is_final": any(marker in state_key for marker in FINAL_MARKERS),
        "state_raw": reads["final_state"]["text"],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "reads": reads,
    }
    out["result_complete"] = bool(
        out["home_team_raw"] and out["away_team_raw"]
        and out["home_goals"] is not None and out["away_goals"] is not None
        and out["is_final"]
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="AJAP isolated PaddleOCR PES6 probe")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    payload = probe(args.image)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["result_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
