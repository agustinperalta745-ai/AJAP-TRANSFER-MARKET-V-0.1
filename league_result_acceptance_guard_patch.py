"""Hard reliability guard for AJAP PES6 screenshots.

A result must not be sent to Staff only because OCR confidence on one glyph is
slightly below the generic threshold.  Local OCR already gives us stronger
structural evidence than a single confidence number:
- both sides resolve to official AJAP teams;
- the score is numeric and spatially located on the PES result screen;
- the screen state can independently say final/partial/unknown;
- uploader/team authority is still checked later by the evidence workflow.

This late patch promotes those structurally valid reads above the intake
threshold and keeps scorer extraction independent.  Missing/weak scorer OCR can
never invalidate an otherwise valid result.  For scorer recovery we only accept
names that fuzzy-match a real player in the corresponding AJAP roster and never
allow scorer totals to exceed the official score.
"""

from __future__ import annotations

import difflib

import league_automation_patch as league
import league_local_ocr_patch as local
import pes_username_link_patch as pes_links


_BASE_LOCAL_PAYLOAD = local._local_payload
_RESULT_STRUCTURAL_CONFIDENCE = 0.90
_RESULT_UNKNOWN_STATE_CONFIDENCE = 0.86
_ROSTER_SCORER_MATCH = 0.72


def _candidate_score(payload):
    if not isinstance(payload, dict):
        return None
    return league.parsed_score(
        {
            "kind": "result",
            "home_team": payload.get("home_team"),
            "away_team": payload.get("away_team"),
            "home_goals": payload.get("home_goals"),
            "away_goals": payload.get("away_goals"),
        }
    )


def _promote_result(payload):
    score = _candidate_score(payload)
    if not score:
        return payload

    home, away, hg, ag = score
    out = dict(payload)
    out["home_team"] = home
    out["away_team"] = away
    out["home_goals"] = int(hg)
    out["away_goals"] = int(ag)

    state = str(out.get("match_state") or "unknown").casefold()
    floor = (
        _RESULT_STRUCTURAL_CONFIDENCE
        if state in {"final", "partial"}
        else _RESULT_UNKNOWN_STATE_CONFIDENCE
    )
    try:
        existing = float(out.get("result_confidence") or out.get("confidence") or 0.0)
    except (TypeError, ValueError):
        existing = 0.0
    confidence = max(existing, floor)
    out["result_confidence"] = confidence
    out["confidence"] = confidence
    out["kind"] = "both" if out.get("scorers") else "result"
    notes = str(out.get("notes") or "").strip()
    audit = f"AJAP structural result acceptance={confidence:.2f} state={state}"
    out["notes"] = (notes + (" | " if notes else "") + audit)[:1000]
    return out


def _roster_candidates(guild_id, team):
    if guild_id is None or pes_links.APP is None:
        return []
    try:
        rows = league.roster(pes_links.APP, int(guild_id))
    except Exception:
        return []
    wanted = league.canonical_team(team)
    result = []
    for row in rows:
        try:
            club = league.canonical_team(row["club"])
            name = str(row["name"] or "").strip()
        except Exception:
            continue
        if club == wanted and name:
            result.append(name)
    return result


def _best_roster_name(raw, names):
    key = league.norm(raw)
    if not key:
        return None, 0.0
    best_name, best = None, 0.0
    for name in names:
        nkey = league.norm(name)
        if not nkey:
            continue
        if key == nkey:
            score = 1.0
        elif len(key) >= 4 and (key in nkey or nkey in key):
            score = 0.94
        else:
            score = difflib.SequenceMatcher(None, key, nkey).ratio()
        if score > best:
            best_name, best = name, score
    if best >= _ROSTER_SCORER_MATCH:
        return best_name, best
    return None, best


def _recover_roster_scorers(images, payload):
    if payload.get("scorers"):
        return payload
    score = _candidate_score(payload)
    if not score:
        return payload
    home, away, hg, ag = score
    guild_id = pes_links._RESULT_GUILD_ID.get()
    if guild_id is None:
        return payload

    try:
        pages = local._all_items(images)
    except Exception as exc:
        print(f"WARNING AJAP scorer roster rescue OCR: {type(exc).__name__}: {exc}")
        return payload
    if not pages:
        return payload

    try:
        detected, _detected_conf = local._detect_scorers(pages, home, away)
    except Exception as exc:
        print(f"WARNING AJAP scorer roster rescue parse: {type(exc).__name__}: {exc}")
        return payload
    if not detected:
        return payload

    rosters = {
        home: _roster_candidates(guild_id, home),
        away: _roster_candidates(guild_id, away),
    }
    limits = {home: int(hg), away: int(ag)}
    totals = {home: 0, away: 0}
    merged = {}
    match_scores = []

    for item in detected:
        if not isinstance(item, dict):
            continue
        team = league.canonical_team(item.get("team"))
        if team not in {home, away}:
            continue
        try:
            goals = int(item.get("goals") or 1)
        except (TypeError, ValueError):
            continue
        if goals < 1 or goals > limits[team]:
            continue
        canonical, confidence = _best_roster_name(item.get("player"), rosters.get(team, []))
        if not canonical:
            continue
        key = (league.norm(canonical), team)
        prior = merged.get(key)
        if prior is None or goals > prior["goals"]:
            merged[key] = {"player": canonical, "team": team, "goals": goals}
        match_scores.append(confidence)

    if not merged:
        return payload

    safe = []
    for item in sorted(merged.values(), key=lambda x: (x["team"], x["player"])):
        team = item["team"]
        goals = int(item["goals"])
        if totals[team] + goals > limits[team]:
            continue
        totals[team] += goals
        safe.append(item)
    if not safe:
        return payload

    out = dict(payload)
    out["scorers"] = safe
    out["kind"] = "both"
    # This confidence is about roster identity, not about the official score.
    scorer_conf = min(match_scores) if match_scores else 0.0
    out["scorers_confidence"] = max(float(local.SCORER_CONFIDENCE), scorer_conf)
    out["roster_scorer_rescue"] = True
    notes = str(out.get("notes") or "").strip()
    audit = f"AJAP roster scorer rescue={len(safe)}"
    out["notes"] = (notes + (" | " if notes else "") + audit)[:1000]
    return out


def _local_payload_reliable(images):
    payload = _BASE_LOCAL_PAYLOAD(images)
    payload = _promote_result(payload)
    # Only after the score is structurally valid do we spend a second OCR pass
    # attempting scorer recovery.  Scorer failure never changes result validity.
    if _candidate_score(payload):
        payload = _recover_roster_scorers(images, payload)
        payload = _promote_result(payload)
    return payload


if not getattr(local._local_payload, "_ajap_structural_acceptance", False):
    _local_payload_reliable._ajap_structural_acceptance = True
    _local_payload_reliable._ajap_structural_acceptance_base = _BASE_LOCAL_PAYLOAD
    local._local_payload = _local_payload_reliable

print(
    "AJAP Liga: aceptación estructural de resultados + rescate de goleadores contra plantilla ACTIVO"
)
