"""Fast local OCR routing for AJAP PES6 result screenshots.

RapidOCR is the reliable primary reader because it already understands full PES6
screens, phone letterboxing and scorer tables. Tesseract remains a lightweight
fixed-region fallback, but a Tesseract miss must never turn a clearly readable
capture into an artificial 0% result.
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

_TESS = shutil.which("tesseract")
_BASE_LOCAL_PAYLOAD = local._local_payload
# The structured reader captured the original full-image RapidOCR payload before
# installing its own fallback. Calling it directly avoids recursion back through
# this Tesseract layer while preserving current dynamic crop/scorer helpers.
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
    try:
        text = _run(_prepared(_box(image, frac), scale=3), 7, timeout=1)
    except Exception:
        return []
    return [(text, 0.93)] if text else []


def _digit_from_crop(image, frac):
    try:
        text = _run(
            _prepared(_box(image, frac), scale=7, binary=True),
            10,
            "0123456789",
            timeout=1,
        )
    except Exception:
        return None, ""
    nums = re.findall(r"\d{1,2}", text or "")
    if not nums:
        return None, text
    value = int(nums[0])
    return (value, text) if 0 <= value <= 20 else (None, text)


def _score_side(image, side):
    boxes = (
        ((0.275, 0.225, 0.375, 0.360), (0.255, 0.205, 0.395, 0.385))
        if side == "home"
        else ((0.625, 0.225, 0.725, 0.360), (0.605, 0.205, 0.745, 0.385))
    )
    for index, frac in enumerate(boxes):
        value, text = _digit_from_crop(image, frac)
        if value is not None:
            return value, (0.96 if index == 0 else 0.91), text
    return None


def _state(image):
    reads = []
    try:
        crop = _box(image, (0.18, 0.145, 0.82, 0.72))
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


# Keep the cheap fixed-region Tesseract mechanics available to the structured
# fallback. Crucially, DO NOT replace structured._read_scorers: scorer-table
# reading remains enabled for result+goleador uploads.
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


def _rapidocr_first(images):
    """Use the full reliable reader first; Tesseract is only a second chance."""
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
        print(f"WARNING AJAP Tesseract fallback: {type(exc).__name__}: {exc}")

    # If RapidOCR at least produced diagnostics/partial fields, preserve them
    # rather than erasing everything to a synthetic 0% Tesseract payload.
    if isinstance(rapid_payload, dict):
        details = []
        if tess_error is not None:
            details.append(f"tesseract={type(tess_error).__name__}")
        return _append_note(
            rapid_payload,
            "AJAP OCR fallback agotado" + ((" | " + " | ".join(details)) if details else ""),
        )

    details = []
    if rapid_error is not None:
        details.append(f"rapidocr={type(rapid_error).__name__}: {rapid_error}")
    if tess_error is not None:
        details.append(f"tesseract={type(tess_error).__name__}: {tess_error}")
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
    "AJAP Liga: RapidOCR primario + Tesseract fallback activo "
    "(capturas claras no caen a 0% por un fallo de Tesseract + goleadores habilitados + cero API)"
)
