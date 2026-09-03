"""Compatibility shim for AJAP local OCR.

The retired rapidocr_onnxruntime package does not support Python 3.13. AJAP's
reader uses its old compact return shape, so expose that interface on top of the
current `rapidocr` package, which supports modern Python and bundles the OCR
models in its wheel.
"""

from rapidocr import RapidOCR as _RapidOCR


class RapidOCR:
    def __init__(self, *args, **kwargs):
        self._engine = _RapidOCR()

    def __call__(self, image, *args, **kwargs):
        result = self._engine(image)
        if result is None:
            return [], None

        boxes = getattr(result, "boxes", None)
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None or txts is None or scores is None:
            return [], getattr(result, "elapse", None)

        rows = []
        for box, text, score in zip(boxes, txts, scores):
            try:
                box_value = box.tolist() if hasattr(box, "tolist") else box
                rows.append([box_value, str(text), float(score)])
            except Exception:
                continue
        return rows, getattr(result, "elapse", None)
