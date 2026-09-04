"""Final anti-hallucination guard for AJAP PES6 result team identity.

A team may be accepted automatically only when there is actual evidence for it:
- an exact/near-exact official team name or configured PES alias in the team label; or
- a registered PES username recognized on that scoreboard side.

Uploader club is allowed only as a constrained fallback already implemented by
``league_multisignal_result_patch``: one scoreboard side/opponent must first be
strongly proven and the uploader must be the other different AJPA club. This keeps
cropped PES6 result screens working without restoring loose fuzzy guesses.
"""

from __future__ import annotations

import difflib

import league_automation_patch as league
import league_local_ocr_patch as local
import league_multisignal_result_patch as multisignal
import league_pes6_structured_reader_patch as structured


def _variants():
    seen = set()
    out = []
    for raw, team in ([(team, team) for team in league.TEAMS] + list(league.ALIASES.items())):
        key = league.norm(raw)
        if not key or (key, team) in seen:
            continue
        seen.add((key, team))
        out.append((key, team))
    return out


def _strict_team_match(text):
    """Resolve only strong, unique team text evidence; never loose-guess a club."""
    key = league.norm(str(text or ""))
    if not key:
        return None, 0.0

    ranked = []
    for wanted, team in _variants():
        if key == wanted:
            score = 1.0
        elif min(len(key), len(wanted)) >= 4 and (wanted in key or key in wanted):
            score = 0.97
        else:
            score = difflib.SequenceMatcher(None, key, wanted).ratio()
        ranked.append((score, team, wanted))

    ranked.sort(reverse=True, key=lambda item: item[0])
    if not ranked:
        return None, 0.0
    best_score, best_team, _ = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0

    if best_score >= 0.97:
        return best_team, best_score
    if best_score >= 0.88 and (best_score - second_score) >= 0.08:
        return best_team, best_score
    return None, best_score


def _strict_link_text(text, links):
    """Resolve PES usernames conservatively; a wrong username must not change club."""
    key = structured.pes_links._username_key(text)
    if not key:
        return None, 0.0

    ranked = []
    for wanted, item in (links or {}).items():
        if key == wanted:
            score = 1.0
        elif wanted and min(len(key), len(wanted)) >= 4 and (wanted in key or key in wanted):
            score = 0.98
        else:
            score = difflib.SequenceMatcher(None, key, wanted).ratio()
        ranked.append((score, item))

    ranked.sort(reverse=True, key=lambda item: item[0])
    if not ranked:
        return None, 0.0
    best_score, best_item = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_score >= 0.98 or (best_score >= 0.90 and best_score - second_score >= 0.08):
        return best_item, best_score
    return None, best_score


# Both generic and fixed-region readers resolve team labels through these globals.
local._team_match = _strict_team_match
multisignal._weak_team_match = _strict_team_match
structured._match_link_text = _strict_link_text

# IMPORTANT: keep multisignal._author_club intact. Its fallback is constrained:
# it only completes a missing side when the other side is already strongly proven
# and differs from the uploader's AJPA club, or when the linked PES username proves
# the uploader's scoreboard side. This is required for cropped PES6 screenshots.

print(
    "AJAP Liga: anti-invencion de equipos ACTIVO "
    "(sin fuzzy debil + fallback seguro por DT cuando el rival ya esta probado)"
)
