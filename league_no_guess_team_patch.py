"""Final anti-hallucination guard for AJAP PES6 result team identity.

A team may be accepted automatically only when there is actual evidence for it:
- an exact/near-exact official team name or configured PES alias in the team label; or
- a registered PES username recognized on that scoreboard side.

Do NOT fill a missing side merely from the Discord uploader's club, and do NOT
accept loose fuzzy matches.  If a kitserver shows a wrong/unrelated club label
(e.g. Borussia Dortmund while the AJAP club is Feyenoord), the linked PES username
must resolve that side; otherwise the screenshot goes to Staff review instead of
inventing an opponent.
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
            # OCR is allowed a small spelling error, but only at a very high
            # similarity threshold and only when the winner is clearly unique.
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

# Critical: the uploader's Discord club alone is NOT visual proof that either side
# of the screenshot is that club.  Side identity must come from team text/alias or
# from a PES username actually visible and linked on that side.
multisignal._author_club = lambda guild_id: None

print(
    "AJAP Liga: anti-invencion de equipos ACTIVO "
    "(sin fuzzy debil + sin completar rival por club del uploader)"
)
