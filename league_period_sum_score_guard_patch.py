"""Guard PES6 score OCR with the visible 1er + 2do period rows.

Problem: RapidOCR/OCR.Space can confuse the large FINAL digits with the smaller
period digits in the center grid. When both period rows are clearly present,
their left/right sums are the safest structural proof of the final score.
"""
from __future__ import annotations

import re

import league_local_ocr_patch as local

_BASE_SCORE_FROM_PAGE = local._score_from_page


def _period_label(text: str):
    raw = str(text or "").casefold().strip()
    if re.search(r"\b1\s*(?:er|st)\b", raw):
        return 1
    if re.search(r"\b2\s*(?:do|nd)\b", raw):
        return 2
    return None


def _period_score(rows):
    if not rows:
        return None
    w = float(rows[0]["w"] or 1.0)
    h = float(rows[0]["h"] or 1.0)

    labels = []
    nums = []
    for row in rows:
        label = _period_label(row.get("text"))
        if label:
            labels.append((label, float(row["x"]) / w, float(row["y"]) / h, float(row.get("conf") or 0.0)))
            continue
        text = str(row.get("text") or "").strip()
        if not re.fullmatch(r"\d{1,2}", text):
            continue
        value = int(text)
        if not (0 <= value <= 20):
            continue
        xn = float(row["x"]) / w
        yn = float(row["y"]) / h
        # Period digits live next to the 1er/2do labels, not at the outer large-score positions.
        if 0.34 <= xn <= 0.66 and 0.18 <= yn <= 0.55:
            nums.append((value, xn, yn, float(row.get("conf") or 0.0)))

    found = {}
    for period in (1, 2):
        period_labels = [item for item in labels if item[0] == period]
        if not period_labels:
            continue
        # Prefer the label closest to the center of the score grid.
        _, lx, ly, lconf = min(period_labels, key=lambda item: abs(item[1] - 0.5))
        left = [n for n in nums if n[1] < lx and abs(n[2] - ly) <= 0.035]
        right = [n for n in nums if n[1] > lx and abs(n[2] - ly) <= 0.035]
        if not left or not right:
            continue
        # Nearest number to the label on each side is the period score cell.
        lnum = min(left, key=lambda n: abs(n[1] - lx))
        rnum = min(right, key=lambda n: abs(n[1] - lx))
        found[period] = (lnum[0], rnum[0], min(lconf, lnum[3], rnum[3]))

    if 1 not in found or 2 not in found:
        return None
    hg = int(found[1][0]) + int(found[2][0])
    ag = int(found[1][1]) + int(found[2][1])
    conf = min(float(found[1][2]), float(found[2][2]))
    return hg, ag, max(0.90, conf)


def _score_from_page_guarded(rows):
    period = _period_score(rows)
    if period:
        return period
    return _BASE_SCORE_FROM_PAGE(rows)


local._score_from_page = _score_from_page_guarded
print("AJAP Liga: marcador final protegido por suma 1er+2do cuando ambas filas son legibles")

# Este módulo ya se carga siempre durante el arranque AJPA. Aprovechamos ese
# punto estable para activar la columna deportiva de Radio Pasillo sin crear
# otro proceso ni modificar el flujo principal del bot.
try:
    import radio_pasillo_sports_column_patch  # noqa: F401
except Exception as exc:
    print(
        "WARNING AJAP Radio Pasillo: no se pudo activar la columna deportiva "
        f"({type(exc).__name__}: {exc})"
    )
