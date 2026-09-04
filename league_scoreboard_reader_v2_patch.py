"""AJAP PES6 scoreboard reader v2.

Goal: read ONLY the final-score panel and stop unrelated PES numbers (Categoria,
Puntos, chat, etc.) from becoming a football score.

The previous geometry was deliberately broad and could pair unrelated standalone
integers. V2 uses two independent proofs:

1) large full-time digits in the narrow left/right score lanes;
2) the 1er/2do breakdown in the centre, when OCR can read both periods.

When both proofs exist they must agree. If they disagree, the complete 1er/2do
breakdown wins because it cannot be produced by Categoria/Puntos columns. If a
strict score cannot be proved, return None and let the normal Staff-review path
handle the screenshot; never guess.
"""

from __future__ import annotations

import re

import league_local_ocr_patch as local


_BASE_SCORE_FROM_PAGE = local._score_from_page


def _bbox_size(row):
    try:
        box = row.get("box") or []
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        return max(xs) - min(xs), max(ys) - min(ys)
    except Exception:
        return 0.0, 0.0


def _norm_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _integer(row):
    text = str(row.get("text") or "").strip()
    if not re.fullmatch(r"\d{1,2}", text):
        return None
    value = int(text)
    return value if 0 <= value <= 20 else None


def _full_time_pair(rows):
    """Find the two LARGE central score digits, never outer stats columns."""
    if not rows:
        return None
    w = float(rows[0].get("w") or 1.0)
    h = float(rows[0].get("h") or 1.0)

    # Rare OCR case: both score digits are returned in one central text box.
    combined = []
    for row in rows:
        text = str(row.get("text") or "")
        m = re.search(r"(?<!\d)(\d{1,2})\s*[-:–—]\s*(\d{1,2})(?!\d)", text)
        if not m:
            continue
        hg, ag = int(m.group(1)), int(m.group(2))
        if not (0 <= hg <= 20 and 0 <= ag <= 20):
            continue
        xn = float(row.get("x") or 0.0) / w
        yn = float(row.get("y") or 0.0) / h
        _bw, bh = _bbox_size(row)
        hn = bh / h
        # Must be the central result panel, not a chat line or stats column.
        if 0.35 <= xn <= 0.65 and 0.20 <= yn <= 0.52 and hn >= 0.022:
            combined.append((hn, float(row.get("conf") or 0.0), hg, ag))
    if combined:
        combined.sort(reverse=True)
        hn, conf, hg, ag = combined[0]
        return hg, ag, max(0.94, conf), "full-score-text"

    left = []
    right = []
    for row in rows:
        value = _integer(row)
        if value is None:
            continue
        xn = float(row.get("x") or 0.0) / w
        yn = float(row.get("y") or 0.0) / h
        bw, bh = _bbox_size(row)
        hn = bh / h
        wn = bw / w
        conf = float(row.get("conf") or 0.0)

        # These lanes match the big PES6 result digits. Categoria/Puntos numbers
        # live much farther toward the outside; 1er/2do digits live closer to 0.5.
        candidate = {
            "value": value,
            "xn": xn,
            "yn": yn,
            "hn": hn,
            "wn": wn,
            "conf": conf,
        }
        if 0.30 <= xn <= 0.455 and 0.20 <= yn <= 0.52 and hn >= 0.022:
            left.append(candidate)
        elif 0.545 <= xn <= 0.70 and 0.20 <= yn <= 0.52 and hn >= 0.022:
            right.append(candidate)

    best = None
    best_rank = -999.0
    for a in left:
        for b in right:
            if abs(a["yn"] - b["yn"]) > 0.055:
                continue
            size_similarity = 1.0 - min(1.0, abs(a["hn"] - b["hn"]) * 20.0)
            symmetry = 1.0 - min(
                1.0,
                abs((0.5 - a["xn"]) - (b["xn"] - 0.5)) * 3.0,
            )
            # PES6 full-time digits are normally around the upper-middle panel;
            # this is a preference, not a hard coordinate.
            center_y = (a["yn"] + b["yn"]) / 2.0
            y_pref = 1.0 - min(1.0, abs(center_y - 0.36) * 3.0)
            rank = (
                min(a["hn"], b["hn"]) * 20.0
                + min(a["conf"], b["conf"])
                + size_similarity * 0.45
                + symmetry * 0.40
                + y_pref * 0.25
            )
            if rank > best_rank:
                best_rank = rank
                best = (a["value"], b["value"], min(a["conf"], b["conf"]))

    if best:
        return best[0], best[1], max(0.93, best[2]), "full-score-digits"
    return None


def _period_marker(text):
    key = _norm_text(text)
    key = key.replace("º", "o")
    if re.search(r"\b1\s*(?:er|ero|st)\b", key):
        return 1
    if re.search(r"\b2\s*(?:do|ndo|nd)\b", key):
        return 2
    return None


def _period_direct(text):
    """Read OCR boxes such as '0 1er 0' or '1 2do 0'."""
    key = _norm_text(text).replace("º", "o")
    patterns = (
        (1, r"(?<!\d)(\d{1,2})\s+1\s*(?:er|ero|st)\s+(\d{1,2})(?!\d)"),
        (2, r"(?<!\d)(\d{1,2})\s+2\s*(?:do|ndo|nd)\s+(\d{1,2})(?!\d)"),
    )
    for period, pattern in patterns:
        m = re.search(pattern, key)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if 0 <= a <= 20 and 0 <= b <= 20:
            return period, a, b
    return None


def _period_breakdown(rows):
    """Return summed 1er+2do score only when BOTH period rows are proved."""
    if not rows:
        return None
    w = float(rows[0].get("w") or 1.0)
    h = float(rows[0].get("h") or 1.0)
    periods = {}

    # First use a complete OCR line when available.
    for row in rows:
        direct = _period_direct(row.get("text"))
        if direct:
            period, home, away = direct
            periods[period] = (home, away, float(row.get("conf") or 0.0))

    # Otherwise locate standalone numbers around the explicit 1er/2do marker.
    for marker in rows:
        period = _period_marker(marker.get("text"))
        if period is None or period in periods:
            continue
        mx = float(marker.get("x") or 0.0) / w
        my = float(marker.get("y") or 0.0) / h
        if not (0.43 <= mx <= 0.57 and 0.18 <= my <= 0.48):
            continue

        left_candidates = []
        right_candidates = []
        for row in rows:
            value = _integer(row)
            if value is None:
                continue
            xn = float(row.get("x") or 0.0) / w
            yn = float(row.get("y") or 0.0) / h
            dy = abs(yn - my)
            if dy > 0.035:
                continue
            item = (dy, -float(row.get("conf") or 0.0), value, float(row.get("conf") or 0.0))
            if 0.405 <= xn < mx - 0.012:
                left_candidates.append(item)
            elif mx + 0.012 < xn <= 0.595:
                right_candidates.append(item)

        if left_candidates and right_candidates:
            left_candidates.sort()
            right_candidates.sort()
            _, _, home, hc = left_candidates[0]
            _, _, away, ac = right_candidates[0]
            periods[period] = (home, away, min(hc, ac, float(marker.get("conf") or 1.0)))

    if 1 not in periods or 2 not in periods:
        return None

    p1 = periods[1]
    p2 = periods[2]
    home = int(p1[0]) + int(p2[0])
    away = int(p1[1]) + int(p2[1])
    if not (0 <= home <= 20 and 0 <= away <= 20):
        return None
    return home, away, max(0.94, min(float(p1[2]), float(p2[2]))), "period-sum"


def score_from_page_v2(rows):
    """Strict PES6 final score extraction with cross-checking."""
    full = _full_time_pair(rows)
    periods = _period_breakdown(rows)

    if full and periods:
        if (full[0], full[1]) == (periods[0], periods[1]):
            return full[0], full[1], 0.995

        # The old 6-7 failure came from unrelated numeric boxes. A complete
        # 1er/2do table is structurally tied to the scoreboard, so reject the
        # conflicting large-pair candidate instead of loading a fabricated score.
        print(
            "WARNING AJAP score v2: full-time digits disagree with 1er/2do; "
            f"full={full[0]}-{full[1]} periods={periods[0]}-{periods[1]}; usando periodos"
        )
        return periods[0], periods[1], 0.975

    if periods:
        return periods[0], periods[1], periods[2]
    if full:
        return full[0], full[1], full[2]

    # Deliberately DO NOT fall back to the old broad numeric pairing. A result
    # that cannot be proved by the actual score panel must go to review.
    return None


# Install after league_multisignal_result_patch: _detect_score resolves this
# function dynamically for every image page.
local._score_from_page = score_from_page_v2

print(
    "AJAP Liga: SCOREBOARD READER V2 listo "
    "(solo panel central + verificacion 1er/2do; Categoria/Puntos excluidos)"
)
