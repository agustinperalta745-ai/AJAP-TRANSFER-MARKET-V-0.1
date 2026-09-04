"""Hardened wrapper for the isolated PES6 PaddleOCR experiment.

This file is still experiment-only. It adds conservative rescues on top of
pes6_paddle_probe.py:
- known/official PES6 team spellings that the base experiment may not yet know;
- final-score recovery from the two *large* numeric OCR boxes in the result
  panel, instead of guessing from period rows, Categoría or Puntos numbers.

It never writes league data.
"""
from __future__ import annotations

import argparse
import json
import numbers
import tempfile
from pathlib import Path

import pes6_paddle_probe as base

_BASE_CANONICAL = base._canonical_team


def _canonical_team(text: str):
    key = base._norm(text)
    hardened = {
        "villarrealc f": "Villarreal",
        "villarreal cf": "Villarreal",
        "villarreal c f": "Villarreal",
        "galatasaray": "Galatasaray",
    }
    for alias, team in hardened.items():
        if key == alias or f" {alias} " in f" {key} ":
            return team
    return _BASE_CANONICAL(text)


def _payload_with_boxes(res):
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
        if texts is None:
            continue
        try:
            texts = [str(x).strip() for x in list(texts)]
        except Exception:
            texts = []
        try:
            raw_scores = inner.get("rec_scores")
            scores = [float(x) for x in list(raw_scores)] if raw_scores is not None else []
        except Exception:
            scores = []

        raw_boxes = inner.get("rec_boxes")
        if raw_boxes is None:
            raw_boxes = inner.get("rec_polys")
        boxes = []
        try:
            raw_list = list(raw_boxes) if raw_boxes is not None else []
            for raw in raw_list:
                vals = raw.tolist() if hasattr(raw, "tolist") else raw
                if isinstance(vals, (list, tuple)) and len(vals) == 4 and all(
                    isinstance(v, numbers.Real) for v in vals
                ):
                    x0, y0, x1, y1 = map(float, vals)
                else:
                    pts = list(vals)
                    xs = [float(p[0]) for p in pts]
                    ys = [float(p[1]) for p in pts]
                    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
                boxes.append([x0, y0, x1, y1])
        except Exception:
            boxes = []
        return texts, scores, boxes
    return [], [], []


def _read_region(ocr, crop, label: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="ajap_paddle_ready_") as tmp:
        path = Path(tmp) / f"{label}.png"
        crop.save(path)
        texts, scores, boxes = [], [], []
        for res in ocr.predict(str(path)):
            t, s, b = _payload_with_boxes(res)
            texts.extend(t)
            scores.extend(s)
            boxes.extend(b)
    clean = [x for x in texts if x]
    return {
        "texts": clean,
        "scores": scores,
        "boxes": boxes,
        "text": " | ".join(clean),
    }


def _large_score_from_state(read: dict):
    """Return (home, away) only when two large opposite-side glyphs prove it."""
    texts = list(read.get("texts") or [])
    boxes = list(read.get("boxes") or [])
    # Paddle may expose one extra geometry box for a detected glyph whose text
    # was filtered from rec_texts. The leading text/box order is still aligned;
    # use only the paired prefix and never fabricate missing boxes.
    if not texts or len(boxes) < len(texts):
        return None

    numeric = []
    for text, box in zip(texts, boxes):
        value = str(text or "").strip()
        if not value.isdigit():
            continue
        number = int(value)
        if not (0 <= number <= 20):
            continue
        x0, y0, x1, y1 = map(float, box)
        width = max(1.0, x1 - x0)
        height = max(1.0, y1 - y0)
        numeric.append({
            "value": number,
            "cx": (x0 + x1) / 2.0,
            "height": height,
            "area": width * height,
            "box": [x0, y0, x1, y1],
        })
    if len(numeric) < 2:
        return None

    valid_boxes = [b for b in boxes if isinstance(b, list) and len(b) == 4]
    if not valid_boxes:
        return None
    max_x = max(float(b[2]) for b in valid_boxes)
    min_x = min(float(b[0]) for b in valid_boxes)
    center = (min_x + max_x) / 2.0

    heights = sorted(item["height"] for item in numeric)
    median_h = heights[len(heights) // 2]
    large = [item for item in numeric if item["height"] >= max(10.0, median_h * 1.28)]
    if len(large) < 2:
        ranked = sorted(numeric, key=lambda item: (item["height"], item["area"]), reverse=True)
        top = ranked[:2]
        if len(top) != 2 or min(i["height"] for i in top) < median_h * 1.18:
            return None
        large = top

    left = sorted(
        (i for i in large if i["cx"] < center),
        key=lambda i: (i["height"], i["area"]),
        reverse=True,
    )
    right = sorted(
        (i for i in large if i["cx"] > center),
        key=lambda i: (i["height"], i["area"]),
        reverse=True,
    )
    if not left or not right:
        return None
    return left[0]["value"], right[0]["value"]


base._canonical_team = _canonical_team
base._read_region = _read_region


def probe(path: Path) -> dict:
    data = base.probe(path)
    read = (data.get("reads") or {}).get("result_state") or {}
    geometry_score = _large_score_from_state(read)
    data["geometry_score"] = list(geometry_score) if geometry_score else None

    # The two large central glyphs are the authoritative score when geometry can
    # prove both sides.  This deliberately ignores Categoría, Puntos and 1er/2do
    # rows even if OCR happens to read those numbers with higher confidence.
    if geometry_score is not None and data.get("is_final") is True:
        previous = (data.get("home_goals"), data.get("away_goals"))
        gh, ga = geometry_score
        data["score_region_read"] = [previous[0], previous[1]]
        data["home_goals"] = gh
        data["away_goals"] = ga
        data["score_source"] = "large_glyph_geometry"
        if previous != (None, None) and previous != (gh, ga):
            data["score_disagreement"] = {
                "isolated_regions": [previous[0], previous[1]],
                "large_glyph_geometry": [gh, ga],
            }

    home = data.get("home_team")
    away = data.get("away_team")
    complete = bool(
        home and away and home != away
        and data.get("home_goals") is not None
        and data.get("away_goals") is not None
        and data.get("is_final") is True
    )
    data["result_complete"] = complete
    if complete:
        data["screen_kind"] = "result"
    elif data.get("is_scorers"):
        data["screen_kind"] = "scorers"
    else:
        data["screen_kind"] = "unknown"
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="AJAP hardened isolated PaddleOCR PES6 probe")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    payload = probe(args.image)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("screen_kind") != "unknown" else 2


if __name__ == "__main__":
    raise SystemExit(main())
