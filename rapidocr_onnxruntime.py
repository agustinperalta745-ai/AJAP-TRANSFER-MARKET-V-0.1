"""Compatibility shim for AJAP local OCR.

AJAP historically imported ``rapidocr_onnxruntime``.  Railway now runs modern
Python, so expose the old compact ``[[box, text, score], ...]`` return shape on
top of the current ``rapidocr`` package.

PES6 result screens are a difficult OCR target: small anti-aliased glyphs,
translucent panels and capture compression.  The parser still has to prove an
official team pair + numeric score before persisting anything, therefore the OCR
layer can safely favour recall over strict text filtering.
"""

from __future__ import annotations

import threading

import numpy as np
from rapidocr import RapidOCR as _RapidOCR


_ALLOWED_CALL_KWARGS = {
    "use_det",
    "use_cls",
    "use_rec",
    "return_word_box",
    "return_single_char_box",
    "text_score",
    "box_thresh",
    "unclip_ratio",
}


class RapidOCR:
    def __init__(self, *args, **kwargs):
        # PES6-friendly defaults.  The previous values lowered box/text scores
        # but left Det.thresh at RapidOCR's 0.30 default; on translucent PES6
        # menus that can produce *zero* detected text before recognition even
        # starts.  Lower the segmentation threshold too and disable the
        # unnecessary 0/180 classifier for horizontal game screenshots.
        params = {
            "Global.text_score": 0.15,
            "Global.use_cls": False,
            "Global.use_vertical_padding": False,
            "Det.thresh": 0.12,
            "Det.box_thresh": 0.18,
            "Det.unclip_ratio": 1.65,
            "Det.use_dilation": True,
        }
        self._engine = _RapidOCR(params=params)
        # RapidOCR updates runtime options in-place.  Serialize calls so two
        # simultaneous Discord uploads cannot change thresholds mid-inference.
        self._call_lock = threading.Lock()

    def __call__(self, image, *args, **kwargs):
        call_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in _ALLOWED_CALL_KWARGS and value is not None
        }
        # AJAP never needs orientation classification for PES screenshots and a
        # classifier failure must not be able to erase an otherwise valid OCR
        # detection/recognition pass.
        call_kwargs.setdefault("use_cls", False)

        with self._call_lock:
            result = self._engine(image, **call_kwargs)
            rows = _rows_from_result(result, image)
            elapsed = _elapsed(result)

            if rows:
                return rows, elapsed

            # Last local-only rescue: if the normal detector sees no text, retry
            # the same image after contrast-oriented transforms.  This remains
            # fully local (OpenCV + ONNX); there is no external/API fallback.
            for variant in _local_rescue_variants(image):
                try:
                    retry = self._engine(
                        variant,
                        use_cls=False,
                        text_score=0.10,
                        box_thresh=0.12,
                        unclip_ratio=1.55,
                    )
                except Exception:
                    continue
                retry_rows = _rows_from_result(retry, variant)
                if retry_rows:
                    return retry_rows, _elapsed(retry)

        return [], elapsed


def _rows_from_result(result, image):
    if result is None:
        return []

    boxes = getattr(result, "boxes", None)
    txts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)

    if txts is None or scores is None:
        return []

    # Normal full OCR result has one box per recognized line.
    if boxes is not None:
        rows = []
        for box, text, score in zip(boxes, txts, scores):
            try:
                clean = str(text or "").strip()
                if not clean:
                    continue
                box_value = box.tolist() if hasattr(box, "tolist") else box
                rows.append([box_value, clean, float(score)])
            except Exception:
                continue
        return rows

    # Recognition-only output has no detection boxes.  AJAP normally calls full
    # OCR, but keeping this compatibility path prevents a future targeted crop
    # pass from being discarded merely because RapidOCR returns TextRecOutput.
    try:
        arr = np.asarray(image)
        h, w = int(arr.shape[0]), int(arr.shape[1])
    except Exception:
        h, w = 1, 1
    synthetic = [[0, 0], [w, 0], [w, h], [0, h]]
    rows = []
    for text, score in zip(txts, scores):
        try:
            clean = str(text or "").strip()
            if clean:
                rows.append([synthetic, clean, float(score)])
        except Exception:
            continue
    return rows


def _local_rescue_variants(image):
    """Return a few cheap local transforms only after the first OCR pass fails."""
    try:
        import cv2

        arr = np.asarray(image)
        if arr.ndim == 2:
            gray = arr.astype(np.uint8, copy=False)
        elif arr.ndim == 3 and arr.shape[2] >= 3:
            # The AJAP caller supplies numpy arrays created from PIL (RGB).
            gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
        else:
            return []

        if gray.dtype != np.uint8:
            gray = np.clip(gray, 0, 255).astype(np.uint8)

        clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8)).apply(gray)
        # Preserve anti-aliased strokes while making translucent menu text much
        # more distinct from the background.
        sharpened = cv2.addWeighted(
            clahe,
            1.55,
            cv2.GaussianBlur(clahe, (0, 0), 1.0),
            -0.55,
            0,
        )
        adaptive = cv2.adaptiveThreshold(
            clahe,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            7,
        )

        return [
            cv2.cvtColor(sharpened, cv2.COLOR_GRAY2RGB),
            cv2.cvtColor(adaptive, cv2.COLOR_GRAY2RGB),
        ]
    except Exception:
        return []


def _elapsed(result):
    value = getattr(result, "elapse", None)
    if value is not None:
        return value
    values = getattr(result, "elapse_list", None)
    if values:
        try:
            return sum(float(item or 0.0) for item in values)
        except Exception:
            return None
    return None
