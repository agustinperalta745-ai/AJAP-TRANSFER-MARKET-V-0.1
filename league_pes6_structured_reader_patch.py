"""Deterministic local PES6 reader for AJAP league screenshots.

This is the final result-reader layer.  It does not call any external vision API.
It keeps the existing full-image RapidOCR pass when it works, but when text
*detector* OCR returns nothing it bypasses detection completely and recognizes
known PES6 screen regions directly:

- left/right PES username header;
- left/right team label;
- left/right full-time score digit;
- post-match/result markers;
- scorer-table rows, matched only against the real AJAP rosters.

The important design change is that a failure of generic text detection can no
longer make a perfectly readable PES6 screenshot become a 0% result.  Region
recognition uses RapidOCR in recognition-only mode (use_det=False), so the
recognizer sees the exact line/digit even when DBNet finds zero text boxes.

Player attribution stays conservative: a scorer is credited only when a roster
name is positively matched.  Blank minute rows are never inherited by the name
above them, and scorer totals can never exceed the official score.
"""

from __future__ import annotations

import difflib
import io
import re
from collections import defaultdict

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import league_automation_patch as league
import league_local_ocr_patch as local
import league_multisignal_result_patch as multisignal
import league_phone_screenshot_crop_patch as phone
import pes_username_link_patch as pes_links

try:
    import league_scorer_continuation_rows_patch as scorer_detail
except Exception:  # pragma: no cover
    scorer_detail = None


_BASE_LOCAL_PAYLOAD = local._local_payload
_RESULT_CONFIDENCE = 0.97
_MIN_PLAYER_MATCH = 0.72


# ---------------------------------------------------------------------------
# Image/recognition helpers
# ---------------------------------------------------------------------------
def _open_frame(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    try:
        image = phone._crop_phone_letterbox(image)
    except Exception:
        pass
    return image


def _box(image: Image.Image, frac):
    x0, y0, x1, y1 = frac
    w, h = image.size
    left = max(0, min(w - 1, int(round(w * x0))))
    top = max(0, min(h - 1, int(round(h * y0))))
    right = max(left + 1, min(w, int(round(w * x1))))
    bottom = max(top + 1, min(h, int(round(h * y1))))
    return image.crop((left, top, right, bottom))


def _variants(crop: Image.Image):
    # Keep the raw anti-aliased line first.  If that is weak, a high-contrast
    # grayscale copy often fixes PES6 translucent UI text without a detector.
    target_h = max(64, min(150, crop.height * 3))
    scale = target_h / max(1, crop.height)
    target_w = max(80, int(round(crop.width * scale)))
    raw = crop.resize((target_w, target_h), Image.Resampling.LANCZOS)
    raw = ImageOps.autocontrast(raw)

    gray = ImageOps.grayscale(raw)
    gray = ImageEnhance.Contrast(gray).enhance(1.75)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.0, percent=170, threshold=2))
    contrast = Image.merge("RGB", (gray, gray, gray))
    return (raw, contrast)


def _recognize_line(image: Image.Image, frac):
    """Recognition-only OCR for one known PES6 UI line/region."""
    crop = _box(image, frac)
    best = []
    for variant in _variants(crop):
        try:
            raw = local._engine()(
                np.asarray(variant),
                use_det=False,
                use_cls=False,
                use_rec=True,
                text_score=0.02,
            )
            rows = raw[0] if isinstance(raw, tuple) else raw
        except Exception as exc:
            print(
                "WARNING AJAP structured recognition: "
                f"{type(exc).__name__}: {exc}"
            )
            continue
        current = []
        for row in rows or []:
            try:
                text = str(row[1] or "").strip()
                conf = float(row[2] or 0.0)
            except Exception:
                continue
            if text:
                current.append((text, conf))
        if current and (not best or max(x[1] for x in current) > max(x[1] for x in best)):
            best = current
    return best


def _joined(reads):
    return " ".join(text for text, _conf in reads if text).strip()


def _best_conf(reads, default=0.0):
    try:
        return max(float(conf) for _text, conf in reads)
    except Exception:
        return float(default)


# ---------------------------------------------------------------------------
# Teams / usernames / score / state
# ---------------------------------------------------------------------------
def _team_from_text(text):
    text = str(text or "").strip()
    if not text:
        return None, 0.0
    team, score = local._team_match(text)
    if team:
        return team, score

    # Recognition-only occasionally leaves a UI prefix/suffix attached. Try
    # progressively smaller token windows before giving up.
    tokens = league.norm(text).split()
    best = (None, 0.0)
    for size in range(min(5, len(tokens)), 0, -1):
        for start in range(0, len(tokens) - size + 1):
            chunk = " ".join(tokens[start : start + size])
            team, score = local._team_match(chunk)
            if team and score > best[1]:
                best = (team, score)
    return best


def _match_link_text(text, links):
    key = pes_links._username_key(text)
    if not key:
        return None, 0.0
    best = None
    best_ratio = 0.0
    for wanted, item in (links or {}).items():
        ratio = 1.0 if key == wanted else difflib.SequenceMatcher(None, key, wanted).ratio()
        # The crop can contain a PES separator or a tiny amount of neighbouring
        # text.  Allow an exact saved username to appear inside the crop string.
        if wanted and (wanted in key or key in wanted):
            ratio = max(ratio, 0.94)
        if ratio > best_ratio:
            best, best_ratio = item, ratio
    return (best, best_ratio) if best_ratio >= 0.72 else (None, best_ratio)


def _parse_score_value(text):
    value = str(text or "").strip()
    nums = re.findall(r"(?<!\d)(\d{1,2})(?!\d)", value)
    if nums:
        number = int(nums[0])
        return number if 0 <= number <= 20 else None

    # Tight digit crops make these common OCR confusions safe to normalize.
    compact = re.sub(r"\s+", "", value).casefold()
    compact = compact.strip("[](){}<>.,:;_-–—")
    aliases = {
        "o": 0, "q": 0, "d": 0,
        "i": 1, "l": 1, "|": 1, "!": 1,
        "z": 2,
        "s": 5,
        "b": 8,
    }
    return aliases.get(compact)


def _read_score_side(image, side):
    boxes = (
        ((0.245, 0.205, 0.405, 0.355), (0.215, 0.175, 0.435, 0.390))
        if side == "home"
        else ((0.595, 0.205, 0.755, 0.355), (0.565, 0.175, 0.785, 0.390))
    )
    best = None
    for frac in boxes:
        reads = _recognize_line(image, frac)
        for text, conf in reads:
            value = _parse_score_value(text)
            if value is None:
                continue
            candidate = (value, max(0.82, float(conf)), text)
            if best is None or candidate[1] > best[1]:
                best = candidate
    return best


def _read_state(image):
    reads = []
    # Header and each post-match menu line are recognized separately so the
    # recognizer never has to decode a multi-line block as one string.
    for frac in (
        (0.31, 0.045, 0.69, 0.125),
        (0.25, 0.405, 0.76, 0.485),
        (0.25, 0.475, 0.76, 0.555),
        (0.25, 0.545, 0.76, 0.625),
        (0.25, 0.615, 0.76, 0.705),
    ):
        reads.extend(_recognize_line(image, frac))
    key = league.norm(_joined(reads))
    final_markers = (
        "resultado",
        "terminar juego",
        "jugar otro partido",
        "detalles del partido",
        "fin del partido",
    )
    partial_markers = (
        "entretiempo",
        "medio tiempo",
        "half time",
        "primer tiempo",
        "1er tiempo",
    )
    if any(marker in key for marker in partial_markers):
        return "partial", reads
    if any(marker in key for marker in final_markers):
        return "final", reads
    return "unknown", reads


def _read_result_frame(image, guild_id):
    links = {}
    if guild_id is not None and pes_links.APP is not None:
        try:
            links = pes_links._active_links(pes_links.APP, int(guild_id))
        except Exception:
            links = {}

    side_data = {}
    for side, team_frac, user_frac in (
        ("home", (0.00, 0.095, 0.495, 0.205), (0.00, 0.000, 0.495, 0.110)),
        ("away", (0.505, 0.095, 1.00, 0.205), (0.505, 0.000, 1.00, 0.110)),
    ):
        team_reads = _recognize_line(image, team_frac)
        user_reads = _recognize_line(image, user_frac)

        team = None
        team_score = 0.0
        for text, conf in team_reads:
            found, match = _team_from_text(text)
            score = min(1.0, max(float(conf), float(match)))
            if found and score > team_score:
                team, team_score = found, score

        linked = None
        link_score = 0.0
        link_text = None
        for text, conf in user_reads:
            item, ratio = _match_link_text(text, links)
            score = min(1.0, max(float(conf), float(ratio)))
            if item and score > link_score:
                linked, link_score, link_text = item, score, text

        if linked:
            team = linked["club"]
            team_score = max(team_score, 0.98)

        side_data[side] = {
            "team": team,
            "team_conf": team_score,
            "team_text": _joined(team_reads),
            "link": linked,
            "link_text": link_text,
            "user_text": _joined(user_reads),
        }

    home_score = _read_score_side(image, "home")
    away_score = _read_score_side(image, "away")
    state, state_reads = _read_state(image)

    # Uploader club is strong supporting identity, but never invent an opponent.
    author_club = None
    try:
        author_club = multisignal._author_club(guild_id)
    except Exception:
        pass
    home = side_data["home"]["team"]
    away = side_data["away"]["team"]
    if author_club in league.TEAMS:
        if home and not away and home != author_club:
            away = author_club
        elif away and not home and away != author_club:
            home = author_club

    if home not in league.TEAMS or away not in league.TEAMS or home == away:
        return None
    if not home_score or not away_score:
        return None

    # A post-match menu/header is the normal final proof.  If the state OCR is
    # uncertain but both official teams and the two large result digits are read
    # from the fixed PES6 post-match geometry, keep state unknown rather than
    # inventing finality; the existing evidence workflow can still ask Staff.
    conf = min(
        max(0.84, side_data["home"]["team_conf"]),
        max(0.84, side_data["away"]["team_conf"]),
        home_score[1],
        away_score[1],
    )
    if state == "final":
        conf = max(conf, _RESULT_CONFIDENCE)
    else:
        conf = max(conf, 0.90)

    payload = {
        "kind": "result",
        "match_state": state,
        "home_team": home,
        "away_team": away,
        "home_goals": int(home_score[0]),
        "away_goals": int(away_score[0]),
        "scorers": [],
        "confidence": min(0.99, conf),
        "result_confidence": min(0.99, conf),
        "scorers_confidence": 0.0,
        "notes": "AJAP PES6 structured local recognition-only",
        "structured_reader": True,
        "structured_raw": {
            "home_team": side_data["home"]["team_text"][:100],
            "away_team": side_data["away"]["team_text"][:100],
            "home_user": side_data["home"]["user_text"][:100],
            "away_user": side_data["away"]["user_text"][:100],
            "home_score": str(home_score[2])[:30],
            "away_score": str(away_score[2])[:30],
            "state": _joined(state_reads)[:160],
        },
    }

    if side_data["home"]["link"]:
        payload["home_pes_username"] = side_data["home"]["link"]["pes_username"]
    if side_data["away"]["link"]:
        payload["away_pes_username"] = side_data["away"]["link"]["pes_username"]
    return payload


# ---------------------------------------------------------------------------
# Scorer-table local fallback
# ---------------------------------------------------------------------------
def _rosters_for_teams(guild_id, home, away):
    if guild_id is None or pes_links.APP is None:
        return {"home": [], "away": []}
    try:
        rows = league.roster(pes_links.APP, int(guild_id))
    except Exception:
        rows = []
    out = {"home": [], "away": []}
    for row in rows:
        try:
            name = str(row["name"] or "").strip()
            club = league.canonical_team(row["club"])
        except Exception:
            continue
        if not name:
            continue
        if club == home:
            out["home"].append(name)
        elif club == away:
            out["away"].append(name)
    return out


def _name_text(value):
    key = league.norm(value)
    tokens = [
        token for token in key.split()
        if not token.isdigit()
        and token not in {"goleador", "goleadores", "gol", "goles", "min", "minuto", "minutos"}
    ]
    return " ".join(tokens)


def _player_match(text, names):
    cleaned = _name_text(text)
    if not cleaned:
        return None, 0.0
    best = None
    best_score = 0.0
    for name in names:
        wanted = league.norm(name)
        if not wanted:
            continue
        if wanted in cleaned:
            score = 0.99
        elif cleaned in wanted and len(cleaned) >= 3:
            score = 0.90
        else:
            score = difflib.SequenceMatcher(None, cleaned, wanted).ratio()
            # Compare token windows as OCR may append the minute list.
            toks = cleaned.split()
            wtoks = wanted.split()
            for size in range(max(1, len(wtoks) - 1), min(len(toks), len(wtoks) + 1) + 1):
                for start in range(0, len(toks) - size + 1):
                    chunk = " ".join(toks[start : start + size])
                    score = max(score, difflib.SequenceMatcher(None, chunk, wanted).ratio())
        if score > best_score:
            best, best_score = name, score
    return (best, best_score) if best_score >= _MIN_PLAYER_MATCH else (None, best_score)


def _goal_count(text):
    count = local._minutes_count(text)
    if count:
        return min(20, int(count))
    # Recognition-only can drop apostrophes while keeping minute numbers.
    nums = [
        int(x) for x in re.findall(r"(?<!\d)(\d{1,3})(?!\d)", str(text or ""))
        if 1 <= int(x) <= 120
    ]
    return min(20, len(nums)) if nums else 0


def _scorer_marker(image):
    reads = []
    for frac in (
        (0.22, 0.08, 0.78, 0.19),
        (0.18, 0.18, 0.82, 0.29),
        (0.33, 0.24, 0.67, 0.35),
    ):
        reads.extend(_recognize_line(image, frac))
    key = league.norm(_joined(reads))
    return ("goleador" in key or "goles" in key), reads


def _read_scorers(frames, result_index, guild_id, payload):
    home = payload.get("home_team")
    away = payload.get("away_team")
    rosters = _rosters_for_teams(guild_id, home, away)
    if not rosters["home"] and not rosters["away"]:
        return [], 0.0

    candidates = {}
    confidence_values = []
    for index, image in enumerate(frames):
        # Result image itself contains chat/menu text and is not a scorer table.
        # Only scan it when a scorer marker is explicitly visible.
        marker, _marker_reads = _scorer_marker(image)
        if index == result_index and not marker:
            continue

        for side, x0, x1 in (("home", 0.015, 0.495), ("away", 0.505, 0.985)):
            names = rosters[side]
            if not names:
                continue
            # Overlapping row bands cover the standard PES6 scorer list without
            # relying on the failed text detector.  Duplicates are consolidated
            # by player+side using MAX goals, never SUM.
            y = 0.255
            while y <= 0.735:
                frac = (x0, y, x1, min(0.82, y + 0.075))
                reads = _recognize_line(image, frac)
                for text, ocr_conf in reads:
                    player, match_conf = _player_match(text, names)
                    if not player:
                        continue
                    goals = _goal_count(text)
                    if goals <= 0 and marker and match_conf >= 0.90:
                        # A clearly recognized named row on an explicit Goleador
                        # screen represents at least one goal even if the tiny
                        # minute glyph is unreadable. Never apply this to an
                        # unmarked image.
                        goals = 1
                    if goals <= 0:
                        continue
                    conf = min(0.99, max(float(ocr_conf), float(match_conf)))
                    key = (league.norm(player), side)
                    prior = candidates.get(key)
                    item = {
                        "player": player,
                        "team": home if side == "home" else away,
                        "goals": int(goals),
                        "conf": conf,
                    }
                    if prior is None or int(goals) > int(prior["goals"]) or (
                        int(goals) == int(prior["goals"]) and conf > float(prior["conf"])
                    ):
                        candidates[key] = item
                    confidence_values.append(conf)
                y += 0.048

    # Official score is the hard ceiling.  If OCR found too many named goals,
    # retain the strongest rows and drop the weakest rather than inventing a fix.
    safe = []
    for side, limit in (
        ("home", int(payload.get("home_goals") or 0)),
        ("away", int(payload.get("away_goals") or 0)),
    ):
        side_items = [item for (_name, s), item in candidates.items() if s == side]
        side_items.sort(key=lambda item: (float(item["conf"]), int(item["goals"])), reverse=True)
        total = 0
        for item in side_items:
            goals = int(item["goals"])
            if total + goals > limit:
                continue
            safe.append({
                "player": item["player"],
                "team": item["team"],
                "goals": goals,
            })
            total += goals

    conf = min(confidence_values) if confidence_values else 0.0
    return safe, min(0.97, max(0.0, conf))


# ---------------------------------------------------------------------------
# Final local payload wrapper
# ---------------------------------------------------------------------------
def _structured_payload(images):
    frames = []
    for data, _mime in images:
        try:
            frames.append(_open_frame(data))
        except Exception as exc:
            print(f"WARNING AJAP structured frame: {type(exc).__name__}: {exc}")
    if not frames:
        raise RuntimeError("No se pudo abrir ninguna imagen PES6")

    guild_id = pes_links._RESULT_GUILD_ID.get()
    result = None
    result_index = None
    for index, image in enumerate(frames):
        try:
            candidate = _read_result_frame(image, guild_id)
        except Exception as exc:
            print(f"WARNING AJAP structured result frame: {type(exc).__name__}: {exc}")
            continue
        if candidate is None:
            continue
        if result is None or float(candidate.get("confidence") or 0.0) > float(result.get("confidence") or 0.0):
            result = candidate
            result_index = index

    if result is None:
        raise RuntimeError("El lector estructurado no pudo probar equipos + marcador")

    scorers, scorer_conf = _read_scorers(frames, result_index, guild_id, result)
    if scorers:
        result["scorers"] = scorers
        result["scorers_confidence"] = scorer_conf
        result["kind"] = "both"
        result["notes"] = (
            str(result.get("notes") or "")
            + f" | goleadores locales={len(scorers)}"
        )[:1000]
    return result


def _local_payload_with_structured_fallback(images):
    base = None
    base_error = None
    try:
        base = _BASE_LOCAL_PAYLOAD(images)
    except Exception as exc:
        base_error = exc
        print(
            "WARNING AJAP full-image OCR -> structured fallback: "
            f"{type(exc).__name__}: {exc}"
        )

    # If the old reader already proved a complete score, keep it.  Still try the
    # structured scorer pass when no players were recovered, because that pass
    # uses roster-constrained recognition-only rows and cannot change the score.
    if isinstance(base, dict):
        try:
            base_ok = bool(
                league.parsed_score(base)
                and float(base.get("result_confidence") or base.get("confidence") or 0.0) >= league.MIN_CONF
            )
        except Exception:
            base_ok = False
        if base_ok:
            if base.get("scorers"):
                return base
            try:
                frames = [_open_frame(data) for data, _mime in images]
                guild_id = pes_links._RESULT_GUILD_ID.get()
                # Locate whichever image looks like the fixed result screen so it
                # can be skipped during generic scorer-row scanning.
                result_index = None
                for i, frame in enumerate(frames):
                    if _read_result_frame(frame, guild_id):
                        result_index = i
                        break
                scorers, scorer_conf = _read_scorers(frames, result_index, guild_id, base)
                if scorers:
                    out = dict(base)
                    out["scorers"] = scorers
                    out["scorers_confidence"] = scorer_conf
                    out["kind"] = "both"
                    notes = str(out.get("notes") or "").strip()
                    out["notes"] = (notes + " | AJAP structured scorer fallback")[:1000]
                    return out
            except Exception as exc:
                print(f"WARNING AJAP structured scorer fallback: {type(exc).__name__}: {exc}")
            return base

    try:
        structured = _structured_payload(images)
        if isinstance(base, dict):
            # Preserve useful audit identity fields from a weak base read.
            for key in (
                "home_pes_username",
                "away_pes_username",
                "pes_usernames",
                "pes_link_applied",
            ):
                if key not in structured and base.get(key):
                    structured[key] = base[key]
        return structured
    except Exception as structured_error:
        if isinstance(base, dict):
            notes = str(base.get("notes") or "").strip()
            detail = f"structured={type(structured_error).__name__}: {structured_error}"
            base["notes"] = (notes + (" | " if notes else "") + detail)[:1000]
            return base
        if base_error is not None:
            raise RuntimeError(
                f"full={type(base_error).__name__}: {base_error} | "
                f"structured={type(structured_error).__name__}: {structured_error}"
            ) from structured_error
        raise


# Install after every older OCR/multisignal patch.
local._local_payload = _local_payload_with_structured_fallback

# No scorer-specific OpenAI request is permitted from the league result path.
if scorer_detail is not None:
    def _no_paid_scorer_repair(*_args, **_kwargs):
        return None
    scorer_detail._repair_vision_sync = _no_paid_scorer_repair

print(
    "AJAP Liga: lector PES6 ESTRUCTURADO LOCAL activo "
    "(full OCR -> regiones recognition-only -> goleadores por roster; cero API)"
)
