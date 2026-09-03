"""Fast local OCR routing for AJAP PES6 result screenshots.

RapidOCR remains the first local reader. Tesseract is the deterministic fallback
for cases where RapidOCR's detector returns no text. The fallback has two layers:
1) the existing structured fixed-region reader;
2) a wider PES6 rescue that uses OCR modes suited to team-name banners and very
   tight score-digit crops.

No paid/external vision API is used here.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import league_automation_patch as league
import league_local_ocr_patch as local
import league_pes6_structured_reader_patch as structured
import pes_username_link_patch as pes_links

_TESS = shutil.which("tesseract")
_BASE_LOCAL_PAYLOAD = local._local_payload
# The structured reader captured the original full-image RapidOCR payload before
# installing its own fallback. Calling it directly avoids recursion back through
# this Tesseract layer while preserving the original full-screen detector path.
_RAPID_LOCAL_PAYLOAD = getattr(structured, "_BASE_LOCAL_PAYLOAD", _BASE_LOCAL_PAYLOAD)


def _box(image, frac):
    x0, y0, x1, y1 = frac
    w, h = image.size
    return image.crop((
        max(0, int(w * x0)), max(0, int(h * y0)),
        min(w, max(1, int(w * x1))), min(h, max(1, int(h * y1))),
    ))


def _prepared(crop, scale=3, *, binary=False):
    target = crop.resize(
        (max(1, crop.width * int(scale)), max(1, crop.height * int(scale))),
        Image.Resampling.LANCZOS,
    )
    gray = ImageOps.grayscale(ImageOps.autocontrast(target))
    gray = ImageEnhance.Contrast(gray).enhance(1.55)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.0, percent=155, threshold=2))
    if binary:
        try:
            import cv2
            arr = np.asarray(gray)
            arr = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            return Image.fromarray(arr)
        except Exception:
            pass
    return gray


def _digit_prepared(crop, scale=7):
    """Preserve the PES6 outlined digit shape better than the old sharpen pass."""
    try:
        import cv2
        arr = np.asarray(ImageOps.grayscale(crop))
        arr = cv2.resize(
            arr,
            None,
            fx=max(1, int(scale)),
            fy=max(1, int(scale)),
            interpolation=cv2.INTER_CUBIC,
        )
        arr = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        return Image.fromarray(arr)
    except Exception:
        # Pillow BICUBIC is still materially safer for the PES6 score font than
        # the old high-sharpen/LANCZOS path when cv2 is unavailable.
        gray = ImageOps.grayscale(crop)
        return gray.resize(
            (max(1, gray.width * int(scale)), max(1, gray.height * int(scale))),
            Image.Resampling.BICUBIC,
        )


def _run(image, psm, whitelist=None, timeout=1):
    if not _TESS:
        raise RuntimeError("Tesseract no está instalado en Railway")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    cmd = [_TESS, "stdin", "stdout", "-l", "eng", "--psm", str(int(psm))]
    if whitelist:
        cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
    proc = subprocess.run(
        cmd,
        input=buf.getvalue(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=max(1, int(timeout)),
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:250])
    return re.sub(r"[ \t]+", " ", proc.stdout.decode("utf-8", "replace")).strip()


def _recognize_line(image, frac):
    """Cheap single-line reader retained for the generic structured fallback."""
    try:
        text = _run(_prepared(_box(image, frac), scale=3), 7, timeout=1)
    except Exception:
        return []
    return [(text, 0.93)] if text else []


def _parse_digit_text(text):
    nums = re.findall(r"\d{1,2}", str(text or ""))
    if not nums:
        return None
    value = int(nums[0])
    return value if 0 <= value <= 20 else None


def _digit_from_crop(image, frac):
    """Read one large score digit using the PES6-safe cubic/Otsu variant first."""
    crop = _box(image, frac)
    for prepared in (
        _digit_prepared(crop, scale=7),
        _prepared(crop, scale=7, binary=True),
    ):
        try:
            text = _run(prepared, 10, "0123456789", timeout=1)
        except Exception:
            continue
        value = _parse_digit_text(text)
        if value is not None:
            return value, text
    return None, ""


def _score_side(image, side):
    # The first pair are tight crops around the actual large PES6 score glyphs.
    # The older wider crops remain as compatibility fallbacks for other captures.
    boxes = (
        (
            (0.295, 0.270, 0.350, 0.375),
            (0.285, 0.245, 0.365, 0.405),
            (0.275, 0.225, 0.375, 0.360),
            (0.255, 0.205, 0.395, 0.385),
        )
        if side == "home"
        else (
            (0.650, 0.270, 0.705, 0.375),
            (0.640, 0.245, 0.720, 0.405),
            (0.625, 0.225, 0.725, 0.360),
            (0.605, 0.205, 0.745, 0.385),
        )
    )
    for index, frac in enumerate(boxes):
        value, text = _digit_from_crop(image, frac)
        if value is not None:
            return value, (0.98 if index == 0 else 0.94), text
    return None


def _state(image):
    reads = []
    try:
        crop = _box(image, (0.18, 0.110, 0.82, 0.72))
        text = _run(_prepared(crop, scale=2), 6, timeout=1)
        if text:
            reads.append((text, 0.94))
    except Exception:
        pass

    key = league.norm(" ".join(x[0] for x in reads))
    if any(x in key for x in (
        "entretiempo", "medio tiempo", "half time", "primer tiempo", "1er tiempo"
    )):
        return "partial", reads
    if any(x in key for x in (
        "resultado", "terminar juego", "jugar otro partido",
        "detalles del partido", "fin del partido", "match details",
        "exit match series", "result", "2nd", "2do",
        "segundo tiempo", "segundo periodo",
    )):
        return "final", reads
    return "unknown", reads


# Keep the generic structured reader operational. Scorer-table reading remains
# installed; only its primitive line/score/state OCR mechanics are replaced.
structured._recognize_line = _recognize_line
structured._read_score_side = _score_side
structured._read_state = _state


def _confidence(payload):
    if not isinstance(payload, dict):
        return 0.0
    try:
        return float(payload.get("result_confidence") or payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _valid_result(payload):
    return bool(
        isinstance(payload, dict)
        and league.parsed_score(payload)
        and _confidence(payload) >= league.MIN_CONF
    )


def _append_note(payload, note):
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    current = str(out.get("notes") or "").strip()
    out["notes"] = (current + (" | " if current else "") + str(note))[:1000]
    return out


def _team_region_reads(image, side):
    """Try page-segmentation modes that actually suit PES6 banner text."""
    if side == "home":
        regions = (
            (0.000, 0.075, 0.505, 0.205),
            (0.000, 0.045, 0.525, 0.245),
        )
    else:
        regions = (
            (0.495, 0.075, 1.000, 0.205),
            (0.475, 0.045, 1.000, 0.245),
        )

    out = []
    seen = set()
    for frac in regions:
        crop = _prepared(_box(image, frac), scale=3)
        # PSM 11 is especially effective on the separated blue/red PES banners;
        # PSM 6 handles the occasional banner+header overlap.
        for psm in (11, 6):
            try:
                text = _run(crop, psm, timeout=1)
            except Exception:
                continue
            text = str(text or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append((text, 0.95 if psm == 11 else 0.92))
    return out


def _team_from_side(image, side):
    best_team = None
    best_conf = 0.0
    raw = []
    for text, ocr_conf in _team_region_reads(image, side):
        raw.append(text)
        candidates = [text] + [line for line in text.splitlines() if line.strip()]
        for candidate in candidates:
            try:
                team, match_conf = structured._team_from_text(candidate)
            except Exception:
                team, match_conf = None, 0.0
            conf = min(0.99, max(float(ocr_conf), float(match_conf or 0.0)))
            if team and conf > best_conf:
                best_team, best_conf = team, conf
    return best_team, best_conf, " | ".join(raw)[:180]


def _wide_result_frame(image):
    """Second fixed-layout proof for captures the original narrow reader misses."""
    home, home_conf, home_raw = _team_from_side(image, "home")
    away, away_conf, away_raw = _team_from_side(image, "away")
    home_score = _score_side(image, "home")
    away_score = _score_side(image, "away")
    state, state_reads = _state(image)

    if home not in league.TEAMS or away not in league.TEAMS or home == away:
        return None
    if not home_score or not away_score:
        return None

    conf = min(
        max(0.90, float(home_conf or 0.0)),
        max(0.90, float(away_conf or 0.0)),
        float(home_score[1]),
        float(away_score[1]),
    )
    if state == "final":
        conf = max(conf, 0.98)
    else:
        conf = max(conf, 0.91)

    return {
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
        "notes": "AJAP Tesseract wide PES6 rescue",
        "structured_reader": True,
        "structured_raw": {
            "home_team": home_raw,
            "away_team": away_raw,
            "home_score": str(home_score[2])[:30],
            "away_score": str(away_score[2])[:30],
            "state": " ".join(x[0] for x in state_reads)[:180],
        },
    }


def _wide_tesseract_payload(images):
    frames = []
    for data, _mime in images:
        try:
            frames.append(structured._open_frame(data))
        except Exception:
            continue
    if not frames:
        raise RuntimeError("No se pudo abrir ninguna imagen para rescate Tesseract")

    best = None
    best_index = None
    for index, frame in enumerate(frames):
        candidate = _wide_result_frame(frame)
        if candidate is None:
            continue
        if best is None or _confidence(candidate) > _confidence(best):
            best = candidate
            best_index = index
    if best is None:
        raise RuntimeError("El rescate Tesseract amplio no pudo probar equipos + marcador")

    # Keep scorer support when a second scorer-table screenshot was supplied.
    try:
        guild_id = pes_links._RESULT_GUILD_ID.get()
        scorers, scorer_conf = structured._read_scorers(frames, best_index, guild_id, best)
        if scorers:
            best["scorers"] = scorers
            best["scorers_confidence"] = scorer_conf
            best["kind"] = "both"
            best["notes"] = (best["notes"] + f" | goleadores locales={len(scorers)}")[:1000]
    except Exception as exc:
        best["notes"] = (best["notes"] + f" | scorer_scan={type(exc).__name__}")[:1000]
    return best


def _rapidocr_first(images):
    """RapidOCR -> structured Tesseract -> wide PES6 Tesseract rescue."""
    rapid_payload = None
    rapid_error = None
    try:
        rapid_payload = _RAPID_LOCAL_PAYLOAD(images)
        if _valid_result(rapid_payload):
            return rapid_payload
    except Exception as exc:
        rapid_error = exc
        print(f"WARNING AJAP RapidOCR primary: {type(exc).__name__}: {exc}")

    tess_payload = None
    tess_error = None
    try:
        tess_payload = structured._structured_payload(images)
        if isinstance(tess_payload, dict):
            return _append_note(tess_payload, "AJAP fallback Tesseract fixed regions")
    except Exception as exc:
        tess_error = exc
        print(f"WARNING AJAP Tesseract structured fallback: {type(exc).__name__}: {exc}")

    wide_error = None
    try:
        wide = _wide_tesseract_payload(images)
        if isinstance(wide, dict):
            return wide
    except Exception as exc:
        wide_error = exc
        print(f"WARNING AJAP Tesseract wide rescue: {type(exc).__name__}: {exc}")

    # If RapidOCR produced useful partial diagnostics, do not erase them.
    if isinstance(rapid_payload, dict):
        details = []
        if tess_error is not None:
            details.append(f"tesseract={type(tess_error).__name__}")
        if wide_error is not None:
            details.append(f"wide={type(wide_error).__name__}")
        return _append_note(
            rapid_payload,
            "AJAP OCR fallback agotado" + ((" | " + " | ".join(details)) if details else ""),
        )

    details = []
    if rapid_error is not None:
        details.append(f"rapidocr={type(rapid_error).__name__}: {rapid_error}")
    if tess_error is not None:
        details.append(f"tesseract={type(tess_error).__name__}: {tess_error}")
    if wide_error is not None:
        details.append(f"wide={type(wide_error).__name__}: {wide_error}")
    return {
        "kind": "unknown",
        "match_state": "unknown",
        "home_team": "",
        "away_team": "",
        "home_goals": None,
        "away_goals": None,
        "scorers": [],
        "confidence": 0.0,
        "result_confidence": 0.0,
        "scorers_confidence": 0.0,
        "notes": ("AJAP lectores locales no concluyentes | " + " | ".join(details))[:1000],
    }


local._local_payload = _rapidocr_first

print(
    "AJAP Liga: RapidOCR + Tesseract PES6 reforzado activo "
    "(banner PSM11/6 + score digit cubic/Otsu + wide rescue + goleadores + cero API)"
)
