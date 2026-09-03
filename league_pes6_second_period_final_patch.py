"""PES6 final-state rule used by AJAP result OCR.

The minimal Tesseract state reader now captures period labels and the post-match
menu in one block. This patch therefore reuses that already-read text instead of
launching extra OCR subprocesses just to look for 2nd/2do.
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
    text = " ".join(str(item[0]) for item in (reads or []) if item)
    if _has_second_period(text) or _english_postmatch(text):
        return "final", reads
    return state, reads


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

print("AJAP Liga: 2nd/2do visible => FINAL sin OCR adicional")
