"""Isolated AJAP PES6 OCR experiment using PaddleOCR.

Never imported by production. It classifies fixed PES6 regions, resolves stock
PES6 aliases to AJAP official clubs, and prints diagnostics only.
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

REGIONS = {
    "home_team": (0.00, 0.045, 0.54, 0.23),
    "away_team": (0.46, 0.045, 1.00, 0.23),
    "home_score": (0.255, 0.18, 0.415, 0.43),
    "away_score": (0.585, 0.18, 0.745, 0.43),
    "result_state": (0.16, 0.08, 0.84, 0.73),
    "scorer_header": (0.15, 0.06, 0.85, 0.28),
    "scorer_left": (0.00, 0.16, 0.51, 0.78),
    "scorer_right": (0.49, 0.16, 1.00, 0.78),
}

FINAL_MARKERS = (
    "resultado", "terminar juego", "jugar otro partido", "detalles del partido",
    "2do", "2nd", "result", "match details", "exit match series",
)
SCORER_MARKERS = ("goleador", "goleadores", "scorer", "scorers")

OFFICIAL_TEAMS = (
    "Tottenham Hotspur", "Newcastle United", "Aston Villa", "Everton",
    "West Ham United", "Manchester City", "Bolton Wanderers", "Middlesbrough",
    "Fulham", "Lazio", "Fiorentina", "Torino", "Villarreal", "Sevilla",
    "Real Betis", "Atlético de Madrid", "Real Zaragoza", "Celta de Vigo",
    "Olympique de Lyon", "Olympique de Marsella", "París Saint-Germain (PSG)",
    "Ajax", "Porto", "Benfica", "Feyenoord",
)

ALIASES = {
    "psg": "París Saint-Germain (PSG)",
    "paris saint germain": "París Saint-Germain (PSG)",
    "r zaragoza": "Real Zaragoza",
    "real zaragoza": "Real Zaragoza",
    "zaragoza": "Real Zaragoza",
    "teesside": "Middlesbrough",
    "middlesbrough": "Middlesbrough",
    "middlebrook": "Bolton Wanderers",
    "west london white": "Fulham",
    "west lindo white": "Fulham",
    "west midlands village": "Aston Villa",
    "merseyside blue": "Everton",
    "man blue": "Manchester City",
    "north east london": "Tottenham Hotspur",
    "east london": "West Ham United",
    "olympique lyon": "Olympique de Lyon",
    "lyon": "Olympique de Lyon",
    "olympique marseille": "Olympique de Marsella",
    "marseille": "Olympique de Marsella",
    "marsella": "Olympique de Marsella",
    "atletico madrid": "Atlético de Madrid",
    "atletico": "Atlético de Madrid",
}


def _norm(value) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _canonical_team(text: str):
    key = _norm(text)
    if not key:
        return None
    exact = {_norm(team): team for team in OFFICIAL_TEAMS}
    if key in exact:
        return exact[key]
    if key in ALIASES:
        return ALIASES[key]
    # OCR regions can contain Resultado/user text. Only accept a known literal
    # team/alias appearing as a complete normalized phrase; never fuzzy-invent.
    padded = f" {key} "
    candidates = []
    for alias, team in {**exact, **ALIASES}.items():
        if f" {alias} " in padded:
            candidates.append((len(alias), team))
    return max(candidates)[1] if candidates else None


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
    if image.height < 500 or image.width < 300:
        return image
    arr = np.asarray(image.convert("RGB"))
    visible = np.max(arr, axis=2) > 22
    activity = visible.mean(axis=1)
    active = np.where(activity >= 0.16)[0]
    if len(active) == 0:
        return image
    regions = _merge_regions(active, max_gap=max(10, int(image.height * 0.025)))
    if not regions:
        return image
    def score(region):
        top, bottom = region
        return (bottom - top + 1) * (0.55 + float(activity[top:bottom + 1].mean()))
    top, bottom = max(regions, key=score)
    band_h = bottom - top + 1
    if band_h < max(120, int(image.height * 0.14)) or band_h > int(image.height * 0.86):
        return image
    pad = max(8, int(band_h * 0.025))
    crop = image.crop((0, max(0, top - pad), image.width, min(image.height, bottom + pad + 1)))
    return crop if crop.height >= 120 and crop.width >= 300 else image


def _crop(image: Image.Image, frac) -> Image.Image:
    x0, y0, x1, y1 = frac
    w, h = image.size
    return image.crop((max(0, int(w*x0)), max(0, int(h*y0)), min(w, int(w*x1)), min(h, int(h*y1))))


def _prepare(crop: Image.Image, *, digit=False) -> Image.Image:
    scale = 7 if digit else 3
    target = crop.resize((max(1, crop.width*scale), max(1, crop.height*scale)), Image.Resampling.BICUBIC if digit else Image.Resampling.LANCZOS)
    if digit:
        gray = ImageOps.autocontrast(ImageOps.grayscale(target))
        return ImageEnhance.Contrast(gray).enhance(1.45).convert("RGB")
    return ImageOps.autocontrast(target.convert("RGB"))


def _result_payload(res):
    candidates = []
    try: candidates.append(res.json)
    except Exception: pass
    try: candidates.append(dict(res))
    except Exception: pass
    candidates.append(res)
    for candidate in candidates:
        if callable(candidate):
            try: candidate = candidate()
            except Exception: continue
        if not isinstance(candidate, dict):
            continue
        inner = candidate.get("res") if isinstance(candidate.get("res"), dict) else candidate
        texts = inner.get("rec_texts")
        scores = inner.get("rec_scores")
        if texts is not None:
            try: texts = [str(x).strip() for x in list(texts)]
            except Exception: texts = []
            try: scores = [float(x) for x in list(scores)] if scores is not None else []
            except Exception: scores = []
            return texts, scores
        if inner.get("rec_text"):
            return [str(inner["rec_text"]).strip()], [float(inner.get("rec_score") or 0.0)]
    return [], []


def _read_region(ocr, crop: Image.Image, label: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="ajap_paddle_") as tmp:
        path = Path(tmp) / f"{label}.png"
        crop.save(path)
        texts, scores = [], []
        for res in ocr.predict(str(path)):
            t, s = _result_payload(res)
            texts.extend(t); scores.extend(s)
    return {"texts": [x for x in texts if x], "scores": scores, "text": " | ".join(x for x in texts if x)}


def _parse_digit(text: str):
    vals = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", str(text or "")) if 0 <= int(x) <= 20]
    return vals[0] if len(vals) == 1 else None


def probe(image_path: Path) -> dict:
    from paddleocr import PaddleOCR
    image = Image.open(image_path).convert("RGB")
    frame = _crop_phone_letterbox(image)
    started = time.perf_counter()
    ocr = PaddleOCR(
        ocr_version="PP-OCRv6",
        text_detection_model_name="PP-OCRv6_tiny_det",
        text_recognition_model_name="PP-OCRv6_tiny_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
        device="cpu",
    )
    reads = {}
    for name, frac in REGIONS.items():
        reads[name] = _read_region(ocr, _prepare(_crop(frame, frac), digit=name.endswith("_score")), name)

    result_key = _norm(reads["result_state"]["text"])
    scorer_key = _norm(reads["scorer_header"]["text"])
    is_final = any(_norm(marker) in result_key for marker in FINAL_MARKERS)
    is_scorers = any(_norm(marker) in scorer_key for marker in SCORER_MARKERS)
    home = _canonical_team(reads["home_team"]["text"])
    away = _canonical_team(reads["away_team"]["text"])
    hg = _parse_digit(reads["home_score"]["text"])
    ag = _parse_digit(reads["away_score"]["text"])
    result_complete = bool(home and away and home != away and hg is not None and ag is not None and is_final)
    screen_kind = "result" if result_complete else ("scorers" if is_scorers else "unknown")
    return {
        "source": str(image_path),
        "original_size": list(image.size),
        "normalized_size": list(frame.size),
        "screen_kind": screen_kind,
        "home_team_raw": reads["home_team"]["text"],
        "away_team_raw": reads["away_team"]["text"],
        "home_team": home,
        "away_team": away,
        "home_goals": hg,
        "away_goals": ag,
        "is_final": is_final,
        "is_scorers": is_scorers,
        "scorer_left_raw": reads["scorer_left"]["texts"],
        "scorer_right_raw": reads["scorer_right"]["texts"],
        "state_raw": reads["result_state"]["text"],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "result_complete": result_complete,
        "reads": reads,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AJAP isolated PaddleOCR PES6 probe")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    payload = probe(args.image)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["screen_kind"] != "unknown" else 2

if __name__ == "__main__":
    raise SystemExit(main())
