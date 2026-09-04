"""Hardened wrapper for the isolated PES6 PaddleOCR experiment.

This file is still experiment-only. It adds two conservative rescues on top of
pes6_paddle_probe.py:
- known PES6 team spellings that OCR can glue together (e.g. VillarrealC.F.)
- final-score recovery from the two *large* numeric OCR boxes in the result
  panel, instead of guessing from the period-row number sequence.

It never writes league data.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pes6_paddle_probe as base

_BASE_CANONICAL = base._canonical_team


def _canonical_team(text: str):
    key = base._norm(text)
    glued = {
        "villarrealc f": "Villarreal",
        "villarreal cf": "Villarreal",
        "villarreal c f": "Villarreal",
    }
    if key in glued:
        return glued[key]
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
            scores = [float(x) for x in list(inner.get("rec_scores") or [])]
        except Exception:
            scores = []

        raw_boxes = inner.get("rec_boxes")
        if raw_boxes is None:
            raw_boxes = inner.get("rec_polys")
        boxes = []
        try:
            for raw in list(raw_boxes or []):
                vals = raw.tolist() if hasattr(raw, "tolist") else raw
                # rec_boxes: [x0,y0,x1,y1]. rec_polys: 4 points.
                if isinstance(vals, (list, tuple)) and len(vals) == 4 and all(
                    isinstance(v, (int, float)) for v in vals
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
    """Return (home, away) only when two large numeric boxes prove the score.

    The PES6 final-score glyphs are materially taller than the 1er/2do row
    digits. We require one large numeric box on each side of the result panel.
    If geometry is missing or ambiguous, return None rather than guess.
    """
    texts = list(read.get("texts") or [])
    boxes = list(read.get("boxes") or [])
    if not texts or len(boxes) != len(texts):
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

    max_x = max(float(b[2]) for b in boxes if len(b) == 4)
    min_x = min(float(b[0]) for b in boxes if len(b) == 4)
    center = (min_x + max_x) / 2.0

    heights = sorted(item["height"] for item in numeric)
    median_h = heights[len(heights) // 2]
    # Large final glyphs are usually clearly taller. Keep threshold modest for
    # downsampled Discord screenshots but still reject period-row-only sets.
    large = [item for item in numeric if item["height"] >= max(10.0, median_h * 1.28)]
    if len(large) < 2:
        # As a second conservative geometry test, use the two largest boxes only
        # if they are on opposite sides and each is >= 1.18x the median height.
        ranked = sorted(numeric, key=lambda item: (item["height"], item["area"]), reverse=True)
        top = ranked[:2]
        if len(top) != 2 or min(i["height"] for i in top) < median_h * 1.18:
            return None
        large = top

    left = sorted((i for i in large if i["cx"] < center), key=lambda i: (i["height"], i["area"]), reverse=True)
    right = sorted((i for i in large if i["cx"] > center), key=lambda i: (i["height"], i["area"]), reverse=True)
    if not left or not right:
        return None
    return left[0]["value"], right[0]["value"]


# Patch only the isolated module in this process.
base._canonical_team = _canonical_team
base._read_region = _read_region


def probe(path: Path) -> dict:
    data = base.probe(path)
    read = (data.get("reads") or {}).get("result_state") or {}
    geometry_score = _large_score_from_state(read)
    data["geometry_score"] = list(geometry_score) if geometry_score else None

    hg = data.get("home_goals")
    ag = data.get("away_goals")
    if geometry_score is not None and (hg is None or ag is None):
        gh, ga = geometry_score
        checks = []
        if hg is not None:
            checks.append(int(hg) == gh)
        if ag is not None:
            checks.append(int(ag) == ga)
        # If one isolated crop exists, geometry must agree with it. If neither
        # exists, accept geometry only because both large glyphs are proven by
        # size + opposite-side placement in a screen already marked final.
        if (not checks or all(checks)) and data.get("is_final") is True:
            data["home_goals"] = gh
            data["away_goals"] = ga
            data["score_source"] = "large_glyph_geometry"

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
