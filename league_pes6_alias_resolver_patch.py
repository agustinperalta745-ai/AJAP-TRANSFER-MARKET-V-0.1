"""Authoritative PES6 unlicensed-name resolver for AJPA league results.

The stock PES6 club names supplied by Staff must win before fuzzy matching real
club names. Small OCR mistakes (one/two characters, spacing, punctuation) are
accepted only against this small authoritative alias catalogue.
"""

from __future__ import annotations

import difflib

import league_automation_patch as league

# Staff-confirmed PES6 -> AJPA mappings.
AUTHORITATIVE_PES6_ALIASES = {
    "middlebrook": "Bolton Wanderers",
    "teesside": "Middlesbrough",
    "west lindo white": "Fulham",
    # Common stock spelling / OCR variant kept for compatibility.
    "west london white": "Fulham",
    "west midlands village": "Aston Villa",
    "merseyside blue": "Everton",
    "man blue": "Manchester City",
    "north east london": "Tottenham Hotspur",
}

# Keep any other already-supported aliases (for example East London -> West Ham),
# while making Staff's mappings authoritative for these keys.
league.ALIASES.update(AUTHORITATIVE_PES6_ALIASES)

_ORIGINAL_CANONICAL_TEAM = league.canonical_team
_ALIAS_KEYS = tuple(AUTHORITATIVE_PES6_ALIASES.keys())


def _alias_hit(raw):
    key = league.norm(raw)
    if not key:
        return None

    # Exact normalized PES6 name always wins.
    exact = AUTHORITATIVE_PES6_ALIASES.get(key)
    if exact:
        return exact

    # OCR frequently changes one character or spacing. Compare only against the
    # small Staff-approved alias list to avoid guessing an unrelated club.
    if len(key) >= 5:
        hit = difflib.get_close_matches(key, _ALIAS_KEYS, n=1, cutoff=0.80)
        if hit:
            return AUTHORITATIVE_PES6_ALIASES[hit[0]]
    return None


def canonical_team(raw):
    alias = _alias_hit(raw)
    if alias:
        return alias
    return _ORIGINAL_CANONICAL_TEAM(raw)


canonical_team._ajpa_pes6_alias_resolver = True
league.canonical_team = canonical_team

print(
    "AJPA Liga: resolver PES6 autoritativo + tolerancia OCR activo: "
    + ", ".join(f"{name}->{club}" for name, club in AUTHORITATIVE_PES6_ALIASES.items())
)
