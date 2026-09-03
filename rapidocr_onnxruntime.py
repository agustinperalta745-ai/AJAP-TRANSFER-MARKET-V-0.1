"""Compatibility shim for AJAP local OCR.

The retired rapidocr_onnxruntime package does not support Python 3.13. AJAP's
reader uses its old compact return shape, so expose that interface on top of the
current `rapidocr` package, which supports modern Python and bundles the OCR
models in its wheel.

The league reader intentionally uses lower text/detection thresholds than the
RapidOCR defaults because PES6 result screens contain small, translucent text.
Only this compatibility layer touches those OCR knobs; the league parser still
has to prove official teams + score before persisting a result.
"""

from __future__ import annotations

import threading

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
        # AJAP calls this shim with no legacy model-path arguments. Configure
        # conservative PES6-friendly defaults while keeping dynamic per-pass
        # overrides available through __call__.
        params = {
            "Global.text_score": 0.28,
            "Det.box_thresh": 0.35,
            "Det.unclip_ratio": 1.8,
        }
        self._engine = _RapidOCR(params=params)
        # RapidOCR updates a few runtime thresholds in-place. Serialize calls so
        # simultaneous Discord uploads cannot change those values mid-inference.
        self._call_lock = threading.Lock()

    def __call__(self, image, *args, **kwargs):
        call_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in _ALLOWED_CALL_KWARGS and value is not None
        }
        with self._call_lock:
            result = self._engine(image, **call_kwargs)

        if result is None:
            return [], None

        boxes = getattr(result, "boxes", None)
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None or txts is None or scores is None:
            return [], _elapsed(result)

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
        return rows, _elapsed(result)


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
