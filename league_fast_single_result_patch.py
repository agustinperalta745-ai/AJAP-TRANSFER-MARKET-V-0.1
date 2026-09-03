"""Fast deterministic reader for one ordinary PES6 post-match result screenshot.

This patch exists to keep clear single-image results inside AJAP's 10 second live
OCR budget. It runs only four bounded Tesseract calls (left team, right team,
score panel, final-state panel) before the heavier local OCR chain. Multi-image
uploads are left to the existing scorer-capable reader so this does not disable
or replace scorer extraction.
"""
from __future__ import annotations

import re

import league_automation_patch as league
import league_local_ocr_patch as local
import league_pes6_structured_reader_patch as structured
import league_tesseract_runtime_patch as tess


_BASE_LOCAL_PAYLOAD = local._local_payload


def _team_from_crop(image, side):
    frac = (
        (0.000, 0.040, 0.525, 0.225)
        if side == "home"
        else (0.475, 0.040, 1.000, 0.225)
    )
    crop = tess._prepared(tess._box(image, frac), scale=3)
    text = tess._run(crop, 11, timeout=1)
    candidates = [str(text or "").strip()]
    candidates.extend(line.strip() for line in str(text or "").splitlines() if line.strip())

    best_team = None
    best_match = 0.0
    for candidate in candidates:
        try:
            team, match = structured._team_from_text(candidate)
        except Exception:
            team, match = None, 0.0
        if team and float(match or 0.0) > best_match:
            best_team, best_match = team, float(match or 0.0)
    return best_team, best_match, str(text or "")[:180]


def _score_pair(image):
    # This crop deliberately includes both large total digits. On the PES6 result
    # screen PSM 6 isolates them as a two-number line more reliably than trying
    # to classify each outlined glyph separately (where "1" can look like "4").
    crop = tess._prepared(tess._box(image, (0.200, 0.200, 0.800, 0.450)), scale=5)
    text = tess._run(crop, 6, whitelist="0123456789 ", timeout=1)
    values = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", str(text or ""))]
    values = [x for x in values if 0 <= x <= 20]
    if len(values) != 2:
        return None
    return values[0], values[1], str(text or "")[:80]


def _final_state(image):
    crop = tess._prepared(tess._box(image, (0.180, 0.100, 0.820, 0.720)), scale=2)
    text = tess._run(crop, 11, timeout=1)
    key = league.norm(text)
    if any(marker in key for marker in (
        "entretiempo", "medio tiempo", "half time", "primer tiempo", "1er tiempo"
    )):
        return "partial", str(text or "")[:220]
    if any(marker in key for marker in (
        "resultado", "terminar juego", "jugar otro partido", "detalles del partido",
        "fin del partido", "match details", "exit match series", "result", "2nd",
        "2do", "segundo tiempo", "segundo periodo",
    )):
        return "final", str(text or "")[:220]
    return "unknown", str(text or "")[:220]


def _fast_single_result(images):
    if len(images or []) != 1:
        return None
    data, _mime = images[0]
    image = structured._open_frame(data)

    home, home_match, home_raw = _team_from_crop(image, "home")
    away, away_match, away_raw = _team_from_crop(image, "away")
    scores = _score_pair(image)
    state, state_raw = _final_state(image)

    if home not in league.TEAMS or away not in league.TEAMS or home == away:
        return None
    if not scores:
        return None
    if state != "final":
        return None

    home_goals, away_goals, score_raw = scores
    return {
        "kind": "result",
        "match_state": "final",
        "home_team": home,
        "away_team": away,
        "home_goals": int(home_goals),
        "away_goals": int(away_goals),
        "scorers": [],
        "confidence": 0.98,
        "result_confidence": 0.98,
        "scorers_confidence": 0.0,
        "notes": "AJAP fast single-result Tesseract proof",
        "structured_reader": True,
        "structured_raw": {
            "home_team": home_raw,
            "away_team": away_raw,
            "home_match": round(float(home_match or 0.0), 3),
            "away_match": round(float(away_match or 0.0), 3),
            "score": score_raw,
            "state": state_raw,
        },
    }


def _fast_first(images):
    try:
        payload = _fast_single_result(images)
        if isinstance(payload, dict) and league.parsed_score(payload):
            return payload
    except Exception as exc:
        print(f"WARNING AJAP fast single-result reader: {type(exc).__name__}: {exc}")
    return _BASE_LOCAL_PAYLOAD(images)


local._local_payload = _fast_first
print("AJAP Liga: fast single-result reader activo (4 OCR calls antes del fallback pesado)")
