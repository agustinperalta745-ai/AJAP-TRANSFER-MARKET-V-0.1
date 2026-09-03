"""Tight PES6 score/state crops for the final structured local reader."""

import league_automation_patch as league
import league_pes6_structured_reader_patch as structured


def _score_side(image, side):
    boxes = (
        ((0.275, 0.225, 0.375, 0.360), (0.255, 0.205, 0.395, 0.385))
        if side == "home"
        else ((0.625, 0.225, 0.725, 0.360), (0.605, 0.205, 0.745, 0.385))
    )
    best = None
    for frac in boxes:
        for text, conf in structured._recognize_line(image, frac):
            value = structured._parse_score_value(text)
            if value is None:
                continue
            candidate = (value, max(0.86, float(conf)), text)
            if best is None or candidate[1] > best[1]:
                best = candidate
    return best


def _state(image):
    reads = []
    for frac in (
        (0.390, 0.070, 0.610, 0.140),
        (0.250, 0.430, 0.760, 0.510),
        (0.250, 0.490, 0.760, 0.575),
        (0.250, 0.550, 0.760, 0.640),
        (0.250, 0.615, 0.760, 0.705),
    ):
        reads.extend(structured._recognize_line(image, frac))
    key = league.norm(structured._joined(reads))
    if any(x in key for x in ("entretiempo", "medio tiempo", "half time", "primer tiempo", "1er tiempo")):
        return "partial", reads
    if any(x in key for x in ("resultado", "terminar juego", "jugar otro partido", "detalles del partido", "fin del partido")):
        return "final", reads
    return "unknown", reads


structured._read_score_side = _score_side
structured._read_state = _state
print("AJAP Liga: crops PES6 de marcador/estado ajustados")
