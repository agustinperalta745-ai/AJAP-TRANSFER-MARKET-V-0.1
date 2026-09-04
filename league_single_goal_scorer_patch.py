"""Allow legitimate one-goal PES6 scorer tables to reach roster validation.

The robust scorer reader previously required either the literal OCR word
"Goleador" or at least two minute-formatted rows before it would inspect a page.
That accidentally rejects perfectly valid 1-0 / 0-1 matches when OCR misses the
header: there is only one scorer row, e.g. "John 44'".

A single goal-minute marker is safe enough to activate the scorer parser because
credit is still gated downstream by exact/fuzzy matching against the roster of
the corresponding match side. Arbitrary OCR text is never credited as a player.
"""

from __future__ import annotations

import league_scorer_screen_reliability_patch as scorer


_BASE_PAGE_HAS_SCORER_SHAPE = scorer._page_has_scorer_shape


def _page_has_single_goal_shape(rows) -> bool:
    if _BASE_PAGE_HAS_SCORER_SHAPE(rows):
        return True
    if not rows:
        return False

    h = float(rows[0].get("h") or 1.0)
    for row in rows:
        yn = float(row.get("y") or 0.0) / max(1.0, h)
        if 0.12 <= yn <= 0.80 and scorer._minute_count(row.get("text")) > 0:
            # One minute-formatted goal row is enough to inspect the page. The
            # scorer itself is still accepted only after roster-side validation
            # inside _detect_scorers_reliable.
            return True
    return False


scorer._page_has_scorer_shape = _page_has_single_goal_shape

print(
    "AJAP Liga: goleadores de un solo gol habilitados "
    "(1 minuto visible + validacion obligatoria por plantel)"
)
