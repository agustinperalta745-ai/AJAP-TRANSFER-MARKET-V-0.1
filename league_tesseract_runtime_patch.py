"""Use free local Tesseract as the OCR backend for AJAP's structured PES6 reader."""
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


def _box(image, frac):
    x0, y0, x1, y1 = frac
    w, h = image.size
    return image.crop((
        max(0, int(w*x0)), max(0, int(h*y0)),
        min(w, max(1, int(w*x1))), min(h, max(1, int(h*y1))),
    ))


def _variants(crop, scale=3):
    raw = crop.resize((max(1, crop.width*scale), max(1, crop.height*scale)), Image.Resampling.LANCZOS)
    raw = ImageOps.autocontrast(raw)
    gray = ImageOps.grayscale(raw)
    gray = ImageEnhance.Contrast(gray).enhance(1.45)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.0, percent=150, threshold=2))
    out = [raw, gray]
    try:
        import cv2
        arr = np.asarray(gray)
        th = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        out.append(Image.fromarray(th))
    except Exception:
        pass
    return out


def _run(image, psm, whitelist=None):
    if not _TESS:
        raise RuntimeError("Tesseract no está instalado en Railway")
    buf = io.BytesIO(); image.save(buf, format="PNG")
    cmd = [_TESS, "stdin", "stdout", "-l", "eng", "--psm", str(int(psm))]
    if whitelist:
        cmd += ["-c", f"tessedit_char_whitelist={whitelist}"]
    proc = subprocess.run(cmd, input=buf.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:250])
    return proc.stdout.decode("utf-8", "replace").strip()


def _recognize_line(image, frac):
    """Same interface as the old RapidOCR region reader: [(text, confidence), ...]."""
    crop = _box(image, frac)
    seen = []
    for variant in _variants(crop, scale=3):
        for psm in (6, 7, 11, 12, 13):
            try:
                text = _run(variant, psm)
            except Exception:
                continue
            text = re.sub(r"[ \t]+", " ", str(text or "")).strip()
            if text and text not in seen:
                seen.append(text)
    # Match confidence is established later against official teams/rosters. This
    # value only says the local OCR returned a concrete string from a fixed region.
    return [(text, 0.92) for text in seen]


def _digit_votes(image, side):
    boxes = (
        ((0.295,0.245,0.355,0.350),(0.285,0.235,0.365,0.360),(0.275,0.225,0.375,0.370))
        if side == "home" else
        ((0.635,0.245,0.715,0.350),(0.625,0.235,0.725,0.360),(0.615,0.225,0.735,0.370))
    )
    votes, raw = [], []
    for frac in boxes:
        crop = _box(image, frac)
        for variant in _variants(crop, scale=8):
            for psm in (6, 7, 10, 13):
                try:
                    text = _run(variant, psm, "0123456789")
                except Exception:
                    continue
                if text: raw.append(text)
                nums = re.findall(r"\d{1,2}", text or "")
                if nums:
                    value = int(nums[0])
                    if 0 <= value <= 20: votes.append(value)
    if not votes:
        return None
    value, count = Counter(votes).most_common(1)[0]
    return value, (0.96 if count >= 2 else 0.88), " / ".join(raw[:6])


def _score_side(image, side):
    return _digit_votes(image, side)


def _state(image):
    reads = []
    # Header + post-match menu. Tesseract can tolerate the translucent PES UI.
    for frac in (
        (0.30,0.035,0.70,0.155),
        (0.20,0.39,0.82,0.72),
    ):
        reads.extend(_recognize_line(image, frac))
    text = " ".join(x[0] for x in reads)
    key = league.norm(text)
    if any(x in key for x in ("entretiempo","medio tiempo","half time","primer tiempo","1er tiempo")):
        return "partial", reads
    if (
        ("resultado" in key and ("terminar" in key or "detalles del partido" in key or "jugar otro" in key))
        or "terminar juego" in key
        or "resultado final" in key
        or "fin del partido" in key
    ):
        return "final", reads
    return "unknown", reads


# Replace only OCR mechanics. Team aliases, PES username linking, roster matching,
# official-score ceilings and persistence remain the existing AJAP logic.
structured._recognize_line = _recognize_line
structured._read_score_side = _score_side
structured._read_state = _state


def _tesseract_first(images):
    try:
        return structured._structured_payload(images)
    except Exception as exc:
        print(f"WARNING AJAP Tesseract -> lector legado: {type(exc).__name__}: {exc}")
        return _BASE_LOCAL_PAYLOAD(images)


# Important: do not make a failed RapidOCR detector the first gate anymore.
local._local_payload = _tesseract_first

print("AJAP Liga: Tesseract local PRIMARIO en lector PES6 estructurado (cero API)")
