"""PES6 final-state rule used by AJAP result OCR.

On the PES6 Result screen the centre breakdown lists the first and second
periods (for example ``1st`` / ``2nd`` or ``1er`` / ``2do``).  In this league,
when the second-period row is visible the match is already finished.  This late
patch makes that visual fact authoritative for both the structured Tesseract
reader and the legacy local fallback.
"""
from __future__ import annotations

import re

import league_automation_patch as league
import league_local_ocr_patch as local
import league_pes6_structured_reader_patch as structured

_BASE_STRUCTURED_STATE = structured._read_state
_BASE_LOCAL_STATE = local._match_state


def _has_second_period(text: str) -> bool:
    raw = str(text or "").casefold()
    key = league.norm(raw)
    if re.search(r"\b2\s*(?:nd|do)\b", raw):
        return True
    if re.search(r"\b2\s+(?:nd|do)\b", key):
        return True
    return any(marker in key for marker in (
        "segundo tiempo",
        "segundo periodo",
        "2do tiempo",
        "2do periodo",
    ))


def _english_postmatch(text: str) -> bool:
    key = league.norm(text)
    return (
        ("result" in key and ("match details" in key or "exit match series" in key))
        or "exit match series" in key
    )


def _structured_state(image):
    state, reads = _BASE_STRUCTURED_STATE(image)

    # Read the tiny period labels separately. They sit between the two large
    # score digits and are much easier for OCR when isolated from the whole menu.
    period_reads = []
    for frac in (
        (0.405, 0.185, 0.595, 0.365),
        (0.360, 0.160, 0.640, 0.390),
    ):
        try:
            period_reads.extend(structured._recognize_line(image, frac))
        except Exception:
            pass

    combined_reads = list(reads or []) + period_reads
    text = " ".join(str(item[0]) for item in combined_reads if item)

    # League rule: a visible second-period line means the result is final.
    if _has_second_period(text):
        return "final", combined_reads

    # Also recognise the English PES6 post-match UI used by unpatched clients.
    if _english_postmatch(text):
        return "final", combined_reads

    return state, combined_reads


def _local_state(pages):
    text = "\n".join(
        str(row.get("text") or "")
        for rows in (pages or [])
        for row in (rows or [])
    )
    if _has_second_period(text) or _english_postmatch(text):
        return "final"
    return _BASE_LOCAL_STATE(pages)


structured._read_state = _structured_state
local._match_state = _local_state

print("AJAP Liga: 2nd/2do visible => resultado FINAL")
