"""Multi-signal PES6 result recovery for AJAP.

A clear result must not depend on one OCR string. This late layer combines:
- post-match screen geometry and large score digits;
- official team names read anywhere in the result header;
- the uploader's current AJAP club;
- the uploader's linked PES username when visible in the screenshot;
- existing side-specific PES username mappings.

It also removes the old behaviour that forced confidence to zero merely because
a registered PES username was visible but its side could not be proven. An
ambiguous username remains audit information; it does not invalidate two clear
official teams + a valid score.
"""

from __future__ import annotations

import contextvars
import difflib
import re

import league_automation_patch as league
import league_local_ocr_patch as local
import league_result_feedback_patch as feedback
import pes_username_link_patch as pes_links


_AUTHOR_ID = contextvars.ContextVar("ajap_result_author_id", default=None)
_AUTHOR_DISPLAY = contextvars.ContextVar("ajap_result_author_display", default="")
_BASE_LOCAL_PAYLOAD = local._local_payload
_BASE_RESOLVE_LINKS = pes_links._resolve_payload_with_links
_BASE_FEEDBACK = feedback._feedback_handle


def _bbox_size(row):
    try:
        box = row.get("box") or []
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        return max(xs) - min(xs), max(ys) - min(ys)
    except Exception:
        return 0.0, 0.0


def _score_from_page_big_digits(rows):
    """Prefer the large full-time digits over the small 1er/2do breakdown."""
    if not rows:
        return None
    w = float(rows[0].get("w") or 1.0)
    h = float(rows[0].get("h") or 1.0)

    # Combined score OCR remains strongest when available.
    combined = []
    for row in rows:
        text = str(row.get("text") or "")
        m = re.search(r"(?<!\d)(\d{1,2})\s*[-:–—]\s*(\d{1,2})(?!\d)", text)
        if not m:
            continue
        hg, ag = int(m.group(1)), int(m.group(2))
        if not (0 <= hg <= 20 and 0 <= ag <= 20):
            continue
        xn = float(row.get("x") or 0) / w
        yn = float(row.get("y") or 0) / h
        if 0.18 <= xn <= 0.82 and 0.12 <= yn <= 0.62:
            bw, bh = _bbox_size(row)
            combined.append((float(row.get("conf") or 0), bh / h, hg, ag))
    if combined:
        combined.sort(reverse=True)
        conf, _size, hg, ag = combined[0]
        return hg, ag, max(0.90, conf)

    nums = []
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not re.fullmatch(r"\d{1,2}", text):
            continue
        value = int(text)
        if not (0 <= value <= 20):
            continue
        xn = float(row.get("x") or 0) / w
        yn = float(row.get("y") or 0) / h
        if not (0.18 <= xn <= 0.82 and 0.14 <= yn <= 0.58):
            continue
        bw, bh = _bbox_size(row)
        nums.append({
            "value": value,
            "xn": xn,
            "yn": yn,
            "conf": float(row.get("conf") or 0),
            "bh": bh / h,
            "bw": bw / w,
        })

    best = None
    best_score = -1.0
    for left in nums:
        if not (0.20 <= left["xn"] < 0.48):
            continue
        for right in nums:
            if not (0.52 < right["xn"] <= 0.80):
                continue
            if abs(left["yn"] - right["yn"]) > 0.07:
                continue
            # Full-time digits are visibly larger than the 1er/2do cells. Box
            # height is therefore the strongest discriminator.
            size = min(left["bh"], right["bh"])
            symmetry = 1.0 - min(1.0, abs((0.5-left["xn"]) - (right["xn"]-0.5)) * 2.5)
            y_pref = 1.0 - min(1.0, abs(((left["yn"]+right["yn"])/2.0) - 0.30) * 2.5)
            score = size * 10.0 + left["conf"] + right["conf"] + symmetry * 0.35 + y_pref * 0.25
            if score > best_score:
                best_score = score
                best = (left["value"], right["value"], min(left["conf"], right["conf"]))
    if best:
        return best[0], best[1], max(0.88, best[2])
    return None


# Improve score selection globally for the local reader.
local._score_from_page = _score_from_page_big_digits


def _team_from_display_name(display):
    key = league.norm(display)
    if not key:
        return None
    # Nicknames are normally "usuario | Equipo". Prefer exact suffix/contained
    # official names; aliases are only a fallback.
    ranked = []
    for team in league.TEAMS:
        t = league.norm(team)
        if t and (key.endswith(t) or f" {t} " in f" {key} "):
            ranked.append((len(t), team))
    if ranked:
        return max(ranked)[1]
    for alias, team in league.ALIASES.items():
        a = league.norm(alias)
        if len(a) >= 4 and (key.endswith(a) or f" {a} " in f" {key} "):
            return team
    return None


def _author_club(guild_id):
    author_id = _AUTHOR_ID.get()
    if guild_id is not None and author_id is not None and pes_links.APP is not None:
        try:
            club = pes_links._club_for_user(pes_links.APP, int(guild_id), int(author_id))
            if club in league.TEAMS:
                return club
        except Exception:
            pass
    return _team_from_display_name(_AUTHOR_DISPLAY.get())


def _author_link(guild_id):
    author_id = _AUTHOR_ID.get()
    if guild_id is None or author_id is None or pes_links.APP is None:
        return None
    try:
        row = pes_links._link_for_user(pes_links.APP, int(guild_id), int(author_id))
    except Exception:
        return None
    if not row:
        return None
    return str(row["pes_username"] or "").strip() or None


def _weak_team_match(text):
    key = league.norm(text)
    if not key:
        return None, 0.0
    best_team, best = None, 0.0
    variants = [(team, team) for team in league.TEAMS] + list(league.ALIASES.items())
    for raw, team in variants:
        v = league.norm(raw)
        if not v:
            continue
        if key == v:
            score = 1.0
        elif len(v) >= 4 and (v in key or key in v):
            score = 0.94
        else:
            score = difflib.SequenceMatcher(None, key, v).ratio()
        if score > best:
            best_team, best = team, score
    return (best_team, best) if best >= 0.52 else (None, best)


def _team_occurrences(pages):
    out = []
    for page_i, rows in enumerate(pages):
        if not rows:
            continue
        w = float(rows[0].get("w") or 1)
        h = float(rows[0].get("h") or 1)
        for row in rows:
            yn = float(row.get("y") or 0) / h
            if yn > 0.58:
                continue
            team, score = _weak_team_match(row.get("text"))
            if not team:
                continue
            xn = float(row.get("x") or 0) / w
            side = "home" if xn < 0.47 else "away" if xn > 0.53 else "unknown"
            adjusted = score + (0.12 if side != "unknown" else 0.0)
            out.append({"team": team, "score": adjusted, "side": side, "page": page_i, "row": row})
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def _username_side(pages, username):
    if not username:
        return None, False
    wanted = pes_links._username_key(username)
    seen = False
    best = None
    for rows in pages:
        if not rows:
            continue
        w = float(rows[0].get("w") or 1)
        h = float(rows[0].get("h") or 1)
        for row in rows:
            key = pes_links._username_key(row.get("text"))
            if not key:
                continue
            ratio = 1.0 if key == wanted else difflib.SequenceMatcher(None, key, wanted).ratio()
            if ratio < 0.78:
                continue
            seen = True
            xn = float(row.get("x") or 0) / w
            yn = float(row.get("y") or 0) / h
            # Only the top player panel proves side. Chat lines still prove that
            # the linked PES identity is present, but not which side it belongs to.
            if yn <= 0.30:
                side = "home" if xn < 0.47 else "away" if xn > 0.53 else None
                if side and (best is None or ratio > best[0]):
                    best = (ratio, side)
    return (best[1] if best else None), seen


def _resolve_links_without_zeroing(runtime, guild_id, payload):
    before = dict(payload or {})
    out = _BASE_RESOLVE_LINKS(runtime, guild_id, payload)
    if not isinstance(out, dict):
        return out
    # Old code intentionally set global confidence=0 when a linked username was
    # visible but side-ambiguous. That is too destructive: retain the ambiguity
    # flag for audit, but let team/score evidence decide result validity.
    if out.get("pes_link_ambiguous") and not out.get("pes_link_applied"):
        try:
            prior = float(before.get("result_confidence") or before.get("confidence") or 0.0)
        except (TypeError, ValueError):
            prior = 0.0
        if prior > 0:
            out["confidence"] = max(float(out.get("confidence") or 0.0), prior)
            out["result_confidence"] = max(float(out.get("result_confidence") or 0.0), prior)
    return out


pes_links._resolve_payload_with_links = _resolve_links_without_zeroing


def _complete_from_context(images, payload):
    out = dict(payload or {})
    guild_id = pes_links._RESULT_GUILD_ID.get()
    try:
        pages = local._all_items(images)
    except Exception as exc:
        print(f"WARNING AJAP multisignal OCR: {type(exc).__name__}: {exc}")
        return out
    if not pages:
        return out

    occurrences = _team_occurrences(pages)
    author_club = _author_club(guild_id)
    author_username = _author_link(guild_id)
    author_side, author_username_seen = _username_side(pages, author_username)

    home = league.canonical_team(out.get("home_team"))
    away = league.canonical_team(out.get("away_team"))

    # Strongest visible official team on each side.
    side_best = {}
    for item in occurrences:
        side = item["side"]
        if side not in {"home", "away"} or side in side_best:
            continue
        side_best[side] = item

    if not home and "home" in side_best:
        home = side_best["home"]["team"]
    if not away and "away" in side_best:
        away = side_best["away"]["team"]

    # Exact linked username in the top player panel is authoritative.
    if author_club and author_side == "home":
        home = author_club
    elif author_club and author_side == "away":
        away = author_club

    # If one side is visible and differs from the uploader's official club, the
    # uploader supplies the missing side. This is the common rescue for a team
    # label OCR miss while preserving score orientation.
    if author_club:
        if home and not away and home != author_club:
            away = author_club
        elif away and not home and away != author_club:
            home = author_club

        # A linked PES username visibly present anywhere is enough to establish
        # that the uploader's AJAP identity belongs to this screenshot. When two
        # in-game labels were read but neither is the uploader's current club,
        # replace only a side explicitly indicated by the top panel; otherwise do
        # not guess.
        if author_username_seen and author_side == "home":
            home = author_club
        elif author_username_seen and author_side == "away":
            away = author_club

    if home in league.TEAMS:
        out["home_team"] = home
    if away in league.TEAMS:
        out["away_team"] = away

    # Re-read the score with the large-digit selector even if the earlier pass
    # chose a 1er/2do cell or failed to find a pair.
    preferred_page = None
    if "home" in side_best and "away" in side_best and side_best["home"]["page"] == side_best["away"]["page"]:
        preferred_page = side_best["home"]["page"]
    score = local._detect_score(pages, preferred_page)
    if score:
        out["home_goals"] = int(score[0])
        out["away_goals"] = int(score[1])

    state = local._match_state(pages)
    if state in {"final", "partial"}:
        out["match_state"] = state

    candidate = league.parsed_score({
        "kind": "result",
        "home_team": out.get("home_team"),
        "away_team": out.get("away_team"),
        "home_goals": out.get("home_goals"),
        "away_goals": out.get("away_goals"),
    })
    if candidate:
        sources = []
        if side_best:
            sources.append("team-text")
        if author_club:
            sources.append("uploader-club")
        if author_username_seen:
            sources.append("pes-user")
        if score:
            sources.append("score-geometry")
        if state in {"final", "partial"}:
            sources.append("screen-state")

        # Two official teams + numeric score is enough to leave Staff review.
        # Final/partial state is handled by the normal evidence workflow.
        conf = 0.94 if state in {"final", "partial"} else 0.88
        out["result_confidence"] = max(float(out.get("result_confidence") or 0.0), conf)
        out["confidence"] = out["result_confidence"]
        out["kind"] = "both" if out.get("scorers") else "result"
        out["multisignal_sources"] = sources
        out.pop("pes_link_ambiguous", None)
        notes = str(out.get("notes") or "").strip()
        audit = "AJAP multisignal=" + ",".join(sources)
        out["notes"] = (notes + (" | " if notes else "") + audit)[:1000]
    return out


def _local_payload_multisignal(images):
    payload = _BASE_LOCAL_PAYLOAD(images)
    return _complete_from_context(images, payload)


local._local_payload = _local_payload_multisignal


async def _feedback_with_author_context(runtime, bot, message):
    author = getattr(message, "author", None)
    author_id = getattr(author, "id", None)
    display = getattr(author, "display_name", "") or getattr(author, "name", "") or ""
    token_id = _AUTHOR_ID.set(int(author_id) if author_id is not None else None)
    token_display = _AUTHOR_DISPLAY.set(str(display))
    try:
        return await _BASE_FEEDBACK(runtime, bot, message)
    finally:
        _AUTHOR_DISPLAY.reset(token_display)
        _AUTHOR_ID.reset(token_id)


_feedback_with_author_context._ajap_multisignal_author_context = True
feedback._feedback_handle = _feedback_with_author_context


async def analyze_message(runtime, message, images):
    """Analyze an existing Discord result message with the same live contexts.

    Used by the safe backlog recovery path; it does not post to Staff by itself.
    """
    guild_id = getattr(getattr(message, "guild", None), "id", None)
    author = getattr(message, "author", None)
    author_id = getattr(author, "id", None)
    display = getattr(author, "display_name", "") or getattr(author, "name", "") or ""
    guild_token = pes_links._RESULT_GUILD_ID.set(int(guild_id) if guild_id is not None else None)
    author_token = _AUTHOR_ID.set(int(author_id) if author_id is not None else None)
    display_token = _AUTHOR_DISPLAY.set(str(display))
    try:
        return await league.analyze(images)
    finally:
        _AUTHOR_DISPLAY.reset(display_token)
        _AUTHOR_ID.reset(author_token)
        pes_links._RESULT_GUILD_ID.reset(guild_token)


print("AJAP Liga: lector MULTISEÑAL activo (foto + marcador + equipos + DT + usuario PES)")
