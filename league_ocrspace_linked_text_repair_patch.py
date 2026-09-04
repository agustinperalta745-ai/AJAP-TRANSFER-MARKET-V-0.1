"""Late OCR.Space repair using exact linked PES usernames visible in ParsedText.

PES6 can show a non-AJPA/unlicensed club label in the result header while the
actual AJPA identity is carried by the manager's linked PES username. OCR.Space
already reads those usernames in chat/profile text. This patch uses them only as
a conservative tie-breaker:

- never invent orientation when both sides are unknown;
- repair only when one scoreboard side is already an official AJPA team;
- require the visible linked usernames to identify exactly one other AJPA club;
- preserve the visible score and final/partial state;
- only restore confidence after AJPA's parsed_score validates the full result.
"""
from __future__ import annotations

import league_automation_patch as league
import league_ocrspace_result_bridge_patch as bridge
import league_ocrspace_text_rescue_patch as text_rescue
import pes_username_link_patch as pes_links


def _visible_linked_clubs(texts, guild_id):
    if guild_id is None or pes_links.APP is None:
        return []
    try:
        links = pes_links._active_links(pes_links.APP, int(guild_id))
    except Exception:
        return []

    full = league.norm("\n".join(str(item or "") for item in texts))
    if not full:
        return []

    clubs = []
    for item in links.values():
        username = league.norm(item.get("pes_username"))
        club = league.canonical_team(item.get("club"))
        if not username or len(username) < 4 or club not in league.TEAMS:
            continue
        # Exact normalized substring only. Usernames are user-defined and unique
        # in the AJPA link table, so this is stronger than fuzzy club-name OCR.
        if username in full and club not in clubs:
            clubs.append(club)
    return clubs


def _repair_from_visible_links(payload, texts, guild_id):
    out = dict(payload or {})
    visible = _visible_linked_clubs(texts, guild_id)
    if not visible:
        return out

    home = league.canonical_team(out.get("home_team"))
    away = league.canonical_team(out.get("away_team"))

    # Need one anchored side. If both are missing, visible chat usernames alone
    # do not prove left/right orientation, so force Staff instead of guessing.
    if home in league.TEAMS and away not in league.TEAMS:
        candidates = [club for club in visible if club != home]
        if len(candidates) == 1:
            away = candidates[0]
            out["away_team"] = away
    elif away in league.TEAMS and home not in league.TEAMS:
        candidates = [club for club in visible if club != away]
        if len(candidates) == 1:
            home = candidates[0]
            out["home_team"] = home

    # ParsedText sometimes has the 1er/2do table even when overlay geometry did
    # not yield the two large score digits. Recover only via the existing strict
    # period arithmetic / explicit score helpers.
    if out.get("home_goals") is None or out.get("away_goals") is None:
        joined = "\n".join(str(item or "") for item in texts)
        score = text_rescue._period_score(joined) or text_rescue._explicit_score(joined)
        if score:
            out["home_goals"], out["away_goals"] = int(score[0]), int(score[1])

    probe = {
        "kind": "result",
        "home_team": out.get("home_team"),
        "away_team": out.get("away_team"),
        "home_goals": out.get("home_goals"),
        "away_goals": out.get("away_goals"),
    }
    parsed = league.parsed_score(probe)
    state = str(out.get("match_state") or "unknown").casefold()
    if parsed:
        out["kind"] = "both" if out.get("scorers") else "result"
        if state in {"final", "partial"}:
            conf = 0.94
        else:
            conf = 0.88
        out["result_confidence"] = max(float(out.get("result_confidence") or 0.0), conf)
        out["confidence"] = out["result_confidence"]
        notes = str(out.get("notes") or "").strip()
        audit = "AJPA linked-username ParsedText repair=" + ",".join(visible)
        out["notes"] = (notes + (" | " if notes else "") + audit)[:1000]
    return out


def _payload_with_link_repair(images, engine: str, guild_id: int | None):
    # Reuse the text-rescue pipeline but keep the already fetched ParsedText in
    # this same request, avoiding a second OCR.Space API call.
    pages, texts = text_rescue._collect(images, engine)
    geometry = None
    try:
        geometry = text_rescue._geometry_payload(images, pages, guild_id, engine)
    except Exception as exc:
        print(
            f"WARNING AJPA OCRSPACE linked repair overlay Engine {engine}: "
            f"{type(exc).__name__}: {exc}"
        )

    plain = text_rescue._plain_payload(texts, guild_id, engine)
    result = text_rescue._merge(geometry, plain)
    if not result:
        raise RuntimeError("OCR.Space no produjo un payload utilizable")
    return _repair_from_visible_links(result, texts, guild_id)


bridge._payload_with_engine = _payload_with_link_repair

print(
    "AJPA Liga: OCR.Space linked-username ParsedText repair ACTIVO | "
    "un lado oficial + username(s) enlazado(s) pueden recuperar el rival"
)
