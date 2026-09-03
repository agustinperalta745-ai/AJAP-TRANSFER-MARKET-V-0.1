"""Free local OCR reader for AJAP PES6 result screenshots.

This removes paid vision from the critical path. Railway reads screenshots with a
local RapidOCR/ONNX model and builds the same payload used by the Liga workflow.
OpenAI is optional and disabled as fallback unless AJAP_VISION_ALLOW_PAID_FALLBACK=1.

Safety goals:
- a weak scorer read never blocks a clear score;
- PES username links keep priority over the visible in-game team label;
- local OCR never invents a scorer to make totals match;
- Staff review remains the fallback when local OCR cannot prove the result.
"""

from __future__ import annotations

import difflib
import io
import os
import re
import threading
from collections import defaultdict

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

import league_automation_patch as league
import pes_username_link_patch as pes_links


LOCAL_SENTINEL = "__AJAP_LOCAL_OCR_NO_PAID_API__"
ALLOW_PAID_FALLBACK = str(os.getenv("AJAP_VISION_ALLOW_PAID_FALLBACK") or "0").strip().casefold() in {
    "1", "true", "yes", "si", "sí", "on"
}
SCORER_CONFIDENCE = 0.76
_RESULT_CONFIDENCE = 0.91
_ENGINE = None
_ENGINE_LOCK = threading.Lock()

# The historical evidence handler checks only for the presence of OPENAI_API_KEY
# before calling league.analyze. Give it a harmless sentinel when no real key is
# configured; this module never sends the sentinel anywhere.
if not os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = LOCAL_SENTINEL


_IGNORE_PLAYER_WORDS = {
    "resultado", "goleador", "jugador", "partido", "estadio", "categoria",
    "categoría", "puntos", "terminar juego", "jugar otro partido", "detalles del partido",
    "pasar a selec de equipo", "seleccion", "selección", "cambiar el chat", "chat",
    "1er", "2do", "local", "visitante", "home", "away",
}


def _engine():
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is not None:
            return _ENGINE
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
        print("AJAP Liga local OCR: motor RapidOCR/ONNX cargado")
        return _ENGINE


def _norm(value):
    return league.norm(str(value or ""))


def _box_center(box):
    try:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    except Exception:
        return 0.0, 0.0


def _ocr_one(data: bytes):
    image = Image.open(io.BytesIO(data)).convert("RGB")
    # Mild contrast improvement helps the translucent PES6 menus without
    # destroying thin glyphs. Upscale small native captures for OCR.
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(1.25)
    if image.width < 1000:
        scale = min(2.0, 1200.0 / max(1, image.width))
        image = image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
    arr = np.asarray(image)
    raw = _engine()(arr)
    if isinstance(raw, tuple):
        raw = raw[0]

    items = []
    # rapidocr_onnxruntime returns [[box, text, score], ...].
    for row in raw or []:
        try:
            box, text, conf = row[0], str(row[1]).strip(), float(row[2])
        except Exception:
            continue
        if not text:
            continue
        x, y = _box_center(box)
        items.append({
            "box": box,
            "text": text,
            "conf": conf,
            "x": x,
            "y": y,
            "w": float(image.width),
            "h": float(image.height),
        })
    return items


def _all_items(images):
    pages = []
    for data, _mime in images:
        try:
            rows = _ocr_one(data)
        except Exception as exc:
            print(f"WARNING AJAP local OCR imagen: {type(exc).__name__}: {exc}")
            continue
        if rows:
            pages.append(rows)
    return pages


def _team_variants():
    variants = []
    for team in league.TEAMS:
        variants.append((team, team))
    for alias, team in league.ALIASES.items():
        variants.append((alias, team))
    variants.extend([
        ("middlebrook", "Bolton Wanderers"),
        ("paris saint germain", "París Saint-Germain (PSG)"),
        ("psg", "París Saint-Germain (PSG)"),
    ])
    return variants


def _team_match(text):
    key = _norm(text)
    if not key:
        return None, 0.0
    best_team, best = None, 0.0
    for variant, team in _team_variants():
        v = _norm(variant)
        if not v:
            continue
        if key == v:
            score = 1.0
        elif len(v) >= 4 and (v in key or key in v):
            score = 0.94 if min(len(v), len(key)) >= 4 else 0.80
        else:
            score = difflib.SequenceMatcher(None, key, v).ratio()
        if score > best:
            best_team, best = team, score
    return (best_team, best) if best >= 0.62 else (None, best)


def _detect_teams(pages):
    candidates = []
    for page_i, rows in enumerate(pages):
        for row in rows:
            team, score = _team_match(row["text"])
            if not team:
                continue
            # PES team labels are normally in the top/middle portion. Keep lower
            # matches but slightly penalize them to avoid chat text winning.
            vertical = row["y"] / max(1.0, row["h"])
            adjusted = score * (1.0 if vertical <= 0.72 else 0.82)
            candidates.append((adjusted, team, page_i, row))

    # Keep strongest occurrence per team.
    best_by_team = {}
    for score, team, page_i, row in candidates:
        if team not in best_by_team or score > best_by_team[team][0]:
            best_by_team[team] = (score, page_i, row)
    ranked = sorted(
        [(score, team, page_i, row) for team, (score, page_i, row) in best_by_team.items()],
        reverse=True,
        key=lambda x: x[0],
    )
    if len(ranked) < 2:
        return None

    # Prefer two teams found on the same page and on opposite halves.
    best_pair = None
    best_pair_score = -1.0
    for i in range(min(8, len(ranked))):
        for j in range(i + 1, min(8, len(ranked))):
            a, b = ranked[i], ranked[j]
            if a[1] == b[1]:
                continue
            score = a[0] + b[0]
            if a[2] == b[2]:
                score += 0.20
                ax = a[3]["x"] / max(1.0, a[3]["w"])
                bx = b[3]["x"] / max(1.0, b[3]["w"])
                if (ax < 0.48 < bx) or (bx < 0.48 < ax):
                    score += 0.25
            if score > best_pair_score:
                best_pair, best_pair_score = (a, b), score
    if not best_pair:
        return None
    a, b = best_pair
    if a[2] == b[2]:
        ax, bx = a[3]["x"], b[3]["x"]
        left, right = (a, b) if ax <= bx else (b, a)
    else:
        # If only separate pages expose the labels, retain strongest-first. The
        # score parser can still succeed; linked PES usernames can correct sides.
        left, right = a, b
    return {
        "home_team": left[1],
        "away_team": right[1],
        "team_confidence": min(float(left[0]), float(right[0])),
        "page": left[2] if left[2] == right[2] else None,
    }


def _score_from_page(rows):
    if not rows:
        return None
    w = rows[0]["w"]
    h = rows[0]["h"]

    # First choice: OCR produced the whole score as one line, e.g. "2 - 2".
    for row in rows:
        text = str(row["text"])
        m = re.search(r"(?<!\d)(\d{1,2})\s*[-:–—]\s*(\d{1,2})(?!\d)", text)
        if not m:
            continue
        hg, ag = int(m.group(1)), int(m.group(2))
        if 0 <= hg <= 20 and 0 <= ag <= 20:
            return hg, ag, max(0.86, float(row["conf"]))

    # PES6 result screen commonly renders the two score digits as separate OCR
    # boxes around the centre. Pair standalone integers on opposite halves.
    nums = []
    for row in rows:
        text = str(row["text"]).strip()
        if not re.fullmatch(r"\d{1,2}", text):
            continue
        value = int(text)
        if not (0 <= value <= 20):
            continue
        xn = row["x"] / max(1.0, w)
        yn = row["y"] / max(1.0, h)
        if not (0.24 <= xn <= 0.76 and 0.18 <= yn <= 0.72):
            continue
        nums.append((value, xn, yn, float(row["conf"])))

    pair, pair_score = None, -1.0
    for a in nums:
        for b in nums:
            if a is b:
                continue
            if not (a[1] < 0.5 < b[1]):
                continue
            if abs(a[2] - b[2]) > 0.08:
                continue
            symmetry = 1.0 - min(1.0, abs((0.5 - a[1]) - (b[1] - 0.5)) * 2.0)
            y_pref = 1.0 - min(1.0, abs(((a[2] + b[2]) / 2.0) - 0.43) * 2.0)
            score = a[3] + b[3] + symmetry * 0.25 + y_pref * 0.20
            if score > pair_score:
                pair, pair_score = (a[0], b[0], min(a[3], b[3])), score
    return pair


def _detect_score(pages, preferred_page=None):
    order = list(range(len(pages)))
    if preferred_page is not None and preferred_page in order:
        order.remove(preferred_page)
        order.insert(0, preferred_page)
    best = None
    for page_i in order:
        found = _score_from_page(pages[page_i])
        if not found:
            continue
        hg, ag, conf = found
        candidate = (hg, ag, conf, page_i)
        if best is None or conf > best[2]:
            best = candidate
    return best


def _match_state(pages):
    text = "\n".join(row["text"] for rows in pages for row in rows)
    key = _norm(text)
    final_markers = (
        "terminar juego", "jugar otro partido", "resultado final", "fin del partido",
        "goleador", "detalles del partido",
    )
    partial_markers = ("entretiempo", "medio tiempo", "half time", "1er tiempo", "primer tiempo")
    if any(marker in key for marker in partial_markers):
        return "partial"
    if any(marker in key for marker in final_markers):
        return "final"
    # A PES post-match Resultado screen with menu navigation is also final.
    if "resultado" in key and ("terminar" in key or "partido" in key):
        return "final"
    return "unknown"


def _minutes_count(text):
    text = str(text or "")
    marks = re.findall(r"\b\d{1,3}\s*[\'’](?:\+\d+)?", text)
    if marks:
        return len(marks)
    # OCR occasionally drops apostrophes but keeps multiple minute numbers in a
    # compact neighbouring box. Only use this fallback when a plus sign or two
    # distinct numbers strongly suggest minute data.
    nums = re.findall(r"\b\d{1,3}\b", text)
    if "+" in text and nums:
        return len(nums)
    if len(nums) >= 2:
        return len(nums)
    return 0


def _clean_player_text(text):
    value = str(text or "").strip()
    # Remove minute suffixes when OCR joined name + times into one text box.
    value = re.sub(r"\s+\d{1,3}\s*[\'’].*$", "", value).strip()
    if not value or not re.search(r"[A-Za-zÀ-ÿ]", value):
        return None
    if re.search(r"https?://|discord", value, re.I):
        return None
    key = _norm(value)
    if not key or key in {_norm(x) for x in _IGNORE_PLAYER_WORDS}:
        return None
    if any(token in key for token in ("resultado", "goleador", "categoria", "puntos", "terminar juego", "jugar otro partido", "detalles del partido")):
        return None
    if len(value) > 45:
        return None
    return value


def _detect_scorers(pages, home_team, away_team):
    grouped = {}
    confidences = []
    for rows in pages:
        if not rows:
            continue
        full = _norm(" ".join(row["text"] for row in rows))
        if "goleador" not in full:
            continue
        h = rows[0]["h"]
        w = rows[0]["w"]

        for row in rows:
            yn = row["y"] / max(1.0, h)
            xn = row["x"] / max(1.0, w)
            if not (0.30 <= yn <= 0.73):
                continue
            if 0.47 <= xn <= 0.53:
                continue
            player = _clean_player_text(row["text"])
            if not player:
                continue
            # Skip team labels that also live in the scorer table header.
            tm, tm_score = _team_match(player)
            if tm and tm_score >= 0.78:
                continue
            side = "home" if xn < 0.5 else "away"
            team = home_team if side == "home" else away_team

            count = _minutes_count(row["text"])
            if count == 0:
                # Search same-row neighbour on the same half for goal minutes.
                neighbours = []
                for other in rows:
                    if other is row:
                        continue
                    oxn = other["x"] / max(1.0, w)
                    if (oxn < 0.5) != (xn < 0.5):
                        continue
                    if abs(other["y"] - row["y"]) > max(18.0, h * 0.045):
                        continue
                    c = _minutes_count(other["text"])
                    if c:
                        neighbours.append((abs(other["y"] - row["y"]), c, float(other["conf"])))
                if neighbours:
                    neighbours.sort(key=lambda x: x[0])
                    count = neighbours[0][1]
            if count <= 0:
                continue
            count = min(20, int(count))
            key = (_norm(player), side)
            prior = grouped.get(key)
            record = {
                "player": player[:100],
                "team": team,
                "goals": count,
                "conf": float(row["conf"]),
            }
            # Multiple screenshots may repeat the same scorer: keep maximum,
            # never sum duplicates across evidence images.
            if prior is None or count > int(prior["goals"]):
                grouped[key] = record
            confidences.append(float(row["conf"]))

    scorers = [
        {"player": item["player"], "team": item["team"], "goals": int(item["goals"])}
        for item in grouped.values()
        if item["player"] and item["team"]
    ]
    conf = min(confidences) if confidences else 0.0
    return scorers, conf


def _detect_pes_usernames(pages, guild_id):
    if guild_id is None or pes_links.APP is None:
        return {}, []
    try:
        links = pes_links._active_links(pes_links.APP, int(guild_id))
    except Exception:
        return {}, []
    if not links:
        return {}, []

    side_fields = {}
    found = []
    for rows in pages:
        if not rows:
            continue
        w, h = rows[0]["w"], rows[0]["h"]
        for row in rows:
            key = pes_links._username_key(row["text"])
            match = links.get(key)
            if not match:
                continue
            xn = row["x"] / max(1.0, w)
            yn = row["y"] / max(1.0, h)
            side = "unknown"
            # Only top player-name panels are reliable for side assignment. Chat
            # lines near the bottom may contain both usernames on the same side.
            if yn <= 0.28:
                if xn <= 0.46:
                    side = "home"
                elif xn >= 0.54:
                    side = "away"
            found.append({"username": match["pes_username"], "side": side})
            if side in {"home", "away"} and side not in side_fields:
                side_fields[side] = match["pes_username"]
    return side_fields, found


def _local_payload(images):
    pages = _all_items(images)
    if not pages:
        raise RuntimeError("OCR local no pudo leer texto de las imágenes")

    teams = _detect_teams(pages)
    preferred_page = teams.get("page") if teams else None
    score = _detect_score(pages, preferred_page)
    guild_id = pes_links._RESULT_GUILD_ID.get()

    payload = {
        "kind": "unknown",
        "match_state": _match_state(pages),
        "home_team": teams.get("home_team") if teams else "",
        "away_team": teams.get("away_team") if teams else "",
        "home_goals": score[0] if score else None,
        "away_goals": score[1] if score else None,
        "scorers": [],
        "confidence": 0.0,
        "result_confidence": 0.0,
        "scorers_confidence": 0.0,
        "notes": "AJAP local OCR/ONNX",
    }

    side_fields, usernames = _detect_pes_usernames(pages, guild_id)
    if "home" in side_fields:
        payload["home_pes_username"] = side_fields["home"]
    if "away" in side_fields:
        payload["away_pes_username"] = side_fields["away"]
    if usernames:
        payload["pes_usernames"] = usernames

    # Apply username -> current AJAP club mapping BEFORE score validation. This
    # fixes cases where PES displays an unlicensed/different club name.
    payload = pes_links._resolve_payload_with_links(pes_links.APP, guild_id, payload)

    candidate_score = league.parsed_score({
        "kind": "result",
        "home_team": payload.get("home_team"),
        "away_team": payload.get("away_team"),
        "home_goals": payload.get("home_goals"),
        "away_goals": payload.get("away_goals"),
    })
    if candidate_score:
        team_conf = float(teams.get("team_confidence") if teams else 0.88)
        score_conf = float(score[2] if score else 0.0)
        # Username links are stronger than the visible PES label.
        if payload.get("pes_link_applied"):
            team_conf = max(team_conf, 0.97)
        result_conf = min(_RESULT_CONFIDENCE, max(0.0, min(team_conf, score_conf + 0.06)))
        if result_conf >= league.MIN_CONF:
            payload["result_confidence"] = result_conf
            payload["confidence"] = result_conf
            payload["kind"] = "result"

            scorers, scorer_conf = _detect_scorers(
                pages, payload["home_team"], payload["away_team"]
            )
            if scorers and scorer_conf >= SCORER_CONFIDENCE:
                # Do not allow OCR scorer totals to exceed the official result.
                totals = defaultdict(int)
                safe = []
                for item in scorers:
                    side = "home" if item["team"] == payload["home_team"] else "away"
                    limit = int(payload["home_goals"] if side == "home" else payload["away_goals"])
                    if totals[side] + int(item["goals"]) > limit:
                        continue
                    totals[side] += int(item["goals"])
                    safe.append(item)
                if safe:
                    payload["scorers"] = safe
                    payload["scorers_confidence"] = min(0.95, scorer_conf)
                    payload["kind"] = "both"
    return payload


_BASE_ANALYZE = league.analyze


async def analyze_local_first(images):
    local_error = None
    try:
        payload = await league.asyncio.to_thread(_local_payload, images)
        if isinstance(payload, dict):
            conf = float(payload.get("result_confidence") or payload.get("confidence") or 0.0)
            if league.parsed_score(payload) and conf >= league.MIN_CONF:
                return payload
            # Return a low-confidence local payload when paid fallback is disabled;
            # the normal evidence workflow will route only genuinely unreadable
            # cases to Staff.
            if not ALLOW_PAID_FALLBACK:
                return payload
    except Exception as exc:
        local_error = exc
        print(f"WARNING AJAP local OCR principal: {type(exc).__name__}: {exc}")

    real_key = os.getenv("OPENAI_API_KEY") or ""
    if ALLOW_PAID_FALLBACK and real_key and real_key != LOCAL_SENTINEL:
        return await _BASE_ANALYZE(images)
    if local_error is not None:
        raise local_error
    raise RuntimeError("OCR local no pudo validar la captura y fallback pago está desactivado")


analyze_local_first._ajap_local_ocr = True
analyze_local_first._ajap_local_ocr_base = _BASE_ANALYZE
league.analyze = analyze_local_first

print(
    "AJAP Liga LOCAL OCR activo: Railway/ONNX sin costo por captura • "
    + ("fallback OpenAI habilitado" if ALLOW_PAID_FALLBACK else "fallback OpenAI DESACTIVADO")
)
