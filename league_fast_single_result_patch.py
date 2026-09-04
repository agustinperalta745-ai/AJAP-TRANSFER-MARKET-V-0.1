"""Fast deterministic reader for one ordinary PES6 post-match result screenshot.

This patch keeps clear single-image results inside AJAP's 10 second live OCR
budget. It uses local Tesseract only: left team, right team, the two explicit
1er/2do score rows, and the final-state panel.

CRITICAL SCORE RULE: Categoria/Puntos numbers are never considered. The official
score is reconstructed from the fixed central 1er + 2do rows. Only if those rows
cannot be proven do we try the two tight large-score glyph crops; the old broad
numeric crop is intentionally gone.
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


def _two_score_numbers(text):
    values = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", str(text or ""))]
    values = [x for x in values if 0 <= x <= 20]
    if len(values) != 2:
        return None
    return int(values[0]), int(values[1])


def _read_period_row(image, period):
    """Read one fixed PES6 1er/2do row; outer stats are outside every crop."""
    if int(period) == 1:
        regions = (
            (0.390, 0.285, 0.610, 0.360),
            (0.380, 0.270, 0.620, 0.370),
        )
    else:
        regions = (
            (0.390, 0.345, 0.610, 0.425),
            (0.380, 0.340, 0.620, 0.440),
        )

    attempts = []
    for frac in regions:
        crop = tess._prepared(tess._box(image, frac), scale=6)
        for psm in (7, 6):
            try:
                text = tess._run(crop, psm, timeout=1)
            except Exception:
                continue
            text = str(text or "").strip()
            attempts.append(text)
            pair = _two_score_numbers(text)
            if not pair:
                continue

            # The fixed crop itself proves which period this is. Still require a
            # visible period-like token when OCR preserved one; this rejects an
            # accidental two-number line from an unusual screen.
            key = league.norm(text)
            if int(period) == 1:
                marker_ok = any(x in key for x in ("1er", "ler", "1 er", "1st", "er"))
            else:
                marker_ok = any(x in key for x in ("2do", "2 do", "2nd", "do", "ndo"))
            if marker_ok:
                return pair[0], pair[1], text

    return None


def _tight_large_score_pair(image):
    """Fallback only: read each large total digit from its own narrow lane."""
    home = None
    away = None

    # Narrow crops are intentionally inside the large-score lanes and cannot see
    # Categoria/Puntos columns or the central period digits.
    for frac in (
        (0.285, 0.300, 0.355, 0.455),
        (0.270, 0.270, 0.370, 0.470),
    ):
        value, raw = tess._digit_from_crop(image, frac)
        if value is not None:
            home = (int(value), str(raw or ""))
            break

    for frac in (
        (0.645, 0.300, 0.715, 0.455),
        (0.630, 0.270, 0.730, 0.470),
    ):
        value, raw = tess._digit_from_crop(image, frac)
        if value is not None:
            away = (int(value), str(raw or ""))
            break

    if home is None or away is None:
        return None
    return home[0], away[0], f"tight={home[1]}|{away[1]}"


def _score_pair(image):
    """Official score from 1er+2do; never from arbitrary numbers on the screen."""
    first = _read_period_row(image, 1)
    second = _read_period_row(image, 2)
    if first and second:
        hg = int(first[0]) + int(second[0])
        ag = int(first[1]) + int(second[1])
        if 0 <= hg <= 20 and 0 <= ag <= 20:
            return hg, ag, f"1er={first[2]} | 2do={second[2]}"

    # Some unusual skins can make the tiny period text unreadable. The fallback
    # remains deterministic because each total digit is cropped independently.
    return _tight_large_score_pair(image)


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
        "confidence": 0.99 if "1er=" in score_raw else 0.94,
        "result_confidence": 0.99 if "1er=" in score_raw else 0.94,
        "scorers_confidence": 0.0,
        "notes": "AJAP fast single-result local period-proof",
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
print("AJAP Liga: fast reader v2 activo (1er+2do; Categoria/Puntos excluidos)")
