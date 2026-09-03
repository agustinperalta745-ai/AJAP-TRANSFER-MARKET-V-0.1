"""Minimal local Tesseract backend for AJAP PES6 result screenshots.

Live intake must be fast and deterministic. We only read fixed PES6 regions,
never scan scorer rows, and never run a matrix of OCR modes/variants.
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


def _run(image, psm, whitelist=None, timeout=2):
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
    """Exactly one OCR process for a known one-line PES6 region."""
    try:
        text = _run(_prepared(_box(image, frac), scale=3), 7, timeout=2)
    except Exception:
        return []
    return [(text, 0.93)] if text else []


def _digit_from_crop(image, frac):
    """Exactly one single-character OCR pass."""
    try:
        text = _run(
            _prepared(_box(image, frac), scale=7, binary=True),
            10,
            "0123456789",
            timeout=2,
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
    # Tight crop first. Only pay for the wider crop if the tight one is blank.
    for index, frac in enumerate(boxes):
        value, text = _digit_from_crop(image, frac)
        if value is not None:
            return value, (0.96 if index == 0 else 0.91), text
    return None


def _state(image):
    """One OCR block contains period labels + post-match menu."""
    reads = []
    try:
        crop = _box(image, (0.18, 0.145, 0.82, 0.72))
        text = _run(_prepared(crop, scale=2), 6, timeout=2)
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


def _no_blocking_scorer_scan(_frames, _result_index, _guild_id, _payload):
    return [], 0.0


structured._recognize_line = _recognize_line
structured._read_score_side = _score_side
structured._read_state = _state
structured._read_scorers = _no_blocking_scorer_scan


def _tesseract_first(images):
    try:
        return structured._structured_payload(images)
    except Exception as exc:
        # Do not cascade into another expensive OCR implementation during live
        # intake. Return a weak payload immediately; the evidence workflow sends
        # uncertain captures to Staff instead of keeping Discord loading.
        print(f"WARNING AJAP Tesseract MINIMAL: {type(exc).__name__}: {exc}")
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
            "notes": f"AJAP Tesseract minimal no concluyente: {type(exc).__name__}",
        }


local._local_payload = _tesseract_first

print(
    "AJAP Liga: Tesseract MINIMAL primario "
    "(pocas regiones fijas + sin fallback pesado + sin goleadores bloqueantes + cero API)"
)
