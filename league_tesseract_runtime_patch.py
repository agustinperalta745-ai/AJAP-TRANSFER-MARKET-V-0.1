"""Fast local Tesseract backend for AJAP's structured PES6 result reader.

The previous implementation spawned Tesseract many times for every crop (several
pre-processing variants x several PSM modes) and then scanned dozens of scorer
rows before returning the match.  A single screenshot could therefore launch
hundreds of subprocesses, making result intake slow and also increasing the
chance of contradictory OCR guesses.

This version keeps the same fixed PES6 geometry and validation rules, but:
- uses one primary OCR pass per known text region, with one fallback only if blank;
- reads score digits from two tight crops per side instead of dozens of votes;
- reads the post-match menu in one block, with one header fallback;
- does NOT block the official result on scorer-table OCR. Missing scorers stay in
  AJAP's existing Staff completion flow instead of delaying/corrupting the score.

No external API is used.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
from collections import Counter

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import league_automation_patch as league
import league_local_ocr_patch as local
import league_pes6_structured_reader_patch as structured

_TESS = shutil.which("tesseract")
_BASE_LOCAL_PAYLOAD = local._local_payload
_BASE_READ_SCORERS = structured._read_scorers


def _box(image, frac):
    x0, y0, x1, y1 = frac
    w, h = image.size
    return image.crop((
        max(0, int(w * x0)), max(0, int(h * y0)),
        min(w, max(1, int(w * x1))), min(h, max(1, int(h * y1))),
    ))


def _prepared(crop, scale=3, *, binary=False):
    """One stable high-contrast image instead of a large variant matrix."""
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


def _run(image, psm, whitelist=None, timeout=4):
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
    """Fast fixed-region OCR. Normally one Tesseract process, at most two."""
    crop = _box(image, frac)
    reads = []

    try:
        text = _run(_prepared(crop, scale=3), 7)
        if text:
            reads.append(text)
    except Exception:
        pass

    # Only pay for a second process when the first pass returned nothing.
    if not reads:
        try:
            text = _run(_prepared(crop, scale=3, binary=True), 6)
            if text:
                reads.append(text)
        except Exception:
            pass

    return [(text, 0.93) for text in reads]


def _digit_from_crop(image, frac):
    crop = _box(image, frac)
    texts = []
    # PSM 10 is specifically for one character and is much more stable for the
    # two large PES6 score digits than multi-mode voting.
    for binary in (True, False):
        try:
            text = _run(
                _prepared(crop, scale=7, binary=binary),
                10,
                "0123456789",
                timeout=3,
            )
        except Exception:
            continue
        if text:
            texts.append(text)
        nums = re.findall(r"\d{1,2}", text or "")
        if nums:
            value = int(nums[0])
            if 0 <= value <= 20:
                return value, text
        # Do not run the second variant when the first one already produced a
        # non-empty but unusable string; wider fallback crops handle that case.
        if text:
            break
    return None, " / ".join(texts[:2])


def _score_side(image, side):
    # First crop is tight around the large final digit. Second is a modest safety
    # margin for different resolutions/letterbox crops. No broad OCR voting.
    boxes = (
        ((0.275, 0.225, 0.375, 0.360), (0.255, 0.205, 0.395, 0.385))
        if side == "home"
        else ((0.625, 0.225, 0.725, 0.360), (0.605, 0.205, 0.745, 0.385))
    )
    values = []
    raw = []
    for frac in boxes:
        value, text = _digit_from_crop(image, frac)
        if text:
            raw.append(text)
        if value is not None:
            values.append(value)
            # A clean tight-crop read is enough. The second crop is only a
            # consistency check and must never outvote a valid first digit.
            if len(values) == 1 and frac == boxes[0]:
                continue
    if not values:
        return None
    value = values[0]
    agree = sum(1 for item in values if item == value)
    conf = 0.97 if agree >= 2 else 0.91
    return value, conf, " / ".join(raw[:3])


def _state(image):
    reads = []
    # One block for the post-match menu is faster and more reliable than five
    # separate line subprocesses.
    menu_frac = (0.20, 0.39, 0.82, 0.72)
    try:
        crop = _box(image, menu_frac)
        text = _run(_prepared(crop, scale=3), 6)
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
        "exit match series", "result",
    )):
        return "final", reads

    # Small header fallback only when the menu did not prove state.
    try:
        crop = _box(image, (0.30, 0.035, 0.70, 0.155))
        text = _run(_prepared(crop, scale=3), 7)
        if text:
            reads.append((text, 0.92))
    except Exception:
        pass
    key = league.norm(" ".join(x[0] for x in reads))
    if any(x in key for x in ("resultado", "result", "fin del partido")):
        return "final", reads
    return "unknown", reads


def _no_blocking_scorer_scan(_frames, _result_index, _guild_id, _payload):
    """Result correctness/latency wins; Staff completion handles missing scorers."""
    return [], 0.0


# Replace only OCR mechanics. Team aliases, linked PES usernames, strict team
# identity, official-score ceilings and persistence remain the existing AJAP logic.
structured._recognize_line = _recognize_line
structured._read_score_side = _score_side
structured._read_state = _state
structured._read_scorers = _no_blocking_scorer_scan


def _tesseract_first(images):
    try:
        return structured._structured_payload(images)
    except Exception as exc:
        # Legacy full-image OCR is now a real fallback, never the first gate.
        print(f"WARNING AJAP Tesseract FAST -> lector legado: {type(exc).__name__}: {exc}")
        return _BASE_LOCAL_PAYLOAD(images)


local._local_payload = _tesseract_first

print(
    "AJAP Liga: Tesseract FAST primario "
    "(regiones fijas + score directo + sin barrido bloqueante de goleadores + cero API)"
)
