"""Harden PES6 final-score geometry.

PES6 renders three numeric layers in the same central table:
- two LARGE outer digits = final score;
- two small `1er` digits = first period;
- two small `2do` digits = second period.

The old generic pairing could combine one large final digit with one small period
subtotal (for example turning a visible Ajax 2-2 Feyenoord into 2-0).  Require
final-score candidates to be clearly separated across the outer halves.  If a
busy PES score table is present but no safe outer pair exists, fail closed and
let Staff review it instead of inventing a score.
"""

from __future__ import annotations

import re

import league_local_ocr_patch as local

_BASE_SCORE_FROM_PAGE = local._score_from_page


def _safe_score_from_page(rows):
    if not rows:
        return None
    w = float(rows[0].get("w") or 1.0)
    h = float(rows[0].get("h") or 1.0)

    # Keep explicit OCR lines such as "2 - 2" as the strongest evidence.
    for row in rows:
        text = str(row.get("text") or "")
        match = re.search(r"(?<!\d)(\d{1,2})\s*[-:–—]\s*(\d{1,2})(?!\d)", text)
        if not match:
            continue
        home, away = int(match.group(1)), int(match.group(2))
        if 0 <= home <= 20 and 0 <= away <= 20:
            return home, away, max(0.86, float(row.get("conf") or 0.0))

    nums = []
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not re.fullmatch(r"\d{1,2}", text):
            continue
        value = int(text)
        if not (0 <= value <= 20):
            continue
        xn = float(row.get("x") or 0.0) / max(1.0, w)
        yn = float(row.get("y") or 0.0) / max(1.0, h)
        if not (0.24 <= xn <= 0.76 and 0.18 <= yn <= 0.60):
            continue
        nums.append((value, xn, yn, float(row.get("conf") or 0.0)))

    pair = None
    pair_score = -1.0
    for left in nums:
        for right in nums:
            if left is right or not (left[1] < 0.5 < right[1]):
                continue

            # The LARGE final digits sit much farther apart than the small
            # first/second-period subtotal columns. This rejects cross-pairs
            # like final-left + `1er`-right.
            separation = right[1] - left[1]
            if separation < 0.30:
                continue
            if abs(left[2] - right[2]) > 0.08:
                continue

            symmetry = 1.0 - min(
                1.0,
                abs((0.5 - left[1]) - (right[1] - 0.5)) * 2.0,
            )
            y_mid = (left[2] + right[2]) / 2.0
            y_pref = 1.0 - min(1.0, abs(y_mid - 0.33) * 2.5)
            score = (
                left[3]
                + right[3]
                + symmetry * 0.30
                + y_pref * 0.20
                + min(0.20, max(0.0, separation - 0.30))
            )
            if score > pair_score:
                pair = (left[0], right[0], min(left[3], right[3]))
                pair_score = score

    if pair is not None:
        return pair

    # With 3+ central numeric boxes we are looking at a period table. If no
    # geometrically safe outer pair survived, do not fall back to the old broad
    # matcher because that is exactly how false 2-0/4-0 scores were created.
    if len(nums) >= 3:
        return None

    return _BASE_SCORE_FROM_PAGE(rows)


if not getattr(local._score_from_page, "_ajpa_pes6_final_geometry", False):
    _safe_score_from_page._ajpa_pes6_final_geometry = True
    _safe_score_from_page._ajpa_base = _BASE_SCORE_FROM_PAGE
    local._score_from_page = _safe_score_from_page
    print("AJPA Liga: marcador FINAL PES6 protegido contra dígitos 1er/2do")
