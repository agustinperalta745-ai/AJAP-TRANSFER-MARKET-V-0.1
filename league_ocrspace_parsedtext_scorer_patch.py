from __future__ import annotations

import league_automation_patch as league
import league_ocrspace_result_bridge_patch as bridge
import league_ocrspace_text_rescue_patch as text_rescue
import league_ocrspace_linked_text_repair_patch as linked
import league_scorer_screen_reliability_patch as scorer_rel
import pes_username_link_patch as pes_links


def _rosters(guild_id, home, away):
    runtime = getattr(pes_links, "APP", None)
    out = {home: [], away: []}
    if runtime is None or guild_id is None:
        return out
    try:
        rows = league.roster(runtime, int(guild_id))
    except Exception:
        return out
    wanted = {league.norm(home): home, league.norm(away): away}
    for row in rows:
        try:
            club = league.canonical_team(row["club"]) or str(row["club"] or "").strip()
            name = str(row["name"] or "").strip()
        except Exception:
            continue
        team = wanted.get(league.norm(club))
        key = league.norm(name)
        if team and key:
            out[team].append((name, key))
    return out


def _without_minutes(raw):
    try:
        raw = scorer_rel._MINUTE_RE.sub(" ", str(raw or ""))
    except Exception:
        raw = str(raw or "")
    return league.norm(raw)


def _unique_hit(raw, rosters):
    key = _without_minutes(raw)
    if not key:
        return None
    hits = []
    for team, names in rosters.items():
        for name, pkey in names:
            if key == pkey:
                item = (name, team)
                if item not in hits:
                    hits.append(item)
    return hits[0] if len(hits) == 1 else None


def _recover(texts, guild_id, payload):
    out = dict(payload or {})
    score = league.parsed_score({
        "kind": "result",
        "home_team": out.get("home_team"),
        "away_team": out.get("away_team"),
        "home_goals": out.get("home_goals"),
        "away_goals": out.get("away_goals"),
    })
    if not score:
        return out
    home, away, hg, ag = score
    expected = {home: int(hg), away: int(ag)}
    rosters = _rosters(guild_id, home, away)
    found = {}

    for item in out.get("scorers") or []:
        if not isinstance(item, dict):
            continue
        team = league.canonical_team(item.get("team")) or str(item.get("team") or "")
        name = str(item.get("player") or "").strip()
        try:
            goals = int(item.get("goals") or 0)
        except Exception:
            goals = 0
        if team in expected and name and goals > 0:
            found[(league.norm(name), team)] = {"player": name, "team": team, "goals": goals}

    for page in texts:
        lines = [str(x or "").strip() for x in str(page or "").splitlines() if str(x or "").strip()]
        minute_total = sum(scorer_rel._minute_count(x) for x in lines)
        if minute_total <= 0:
            continue

        # Strongest case: player and minute are on the same ParsedText line.
        for line in lines:
            count = scorer_rel._minute_count(line)
            if count <= 0:
                continue
            hit = _unique_hit(line, rosters)
            if hit:
                name, team = hit
                key = (league.norm(name), team)
                rec = {"player": name, "team": team, "goals": min(20, int(count))}
                if key not in found or rec["goals"] > found[key]["goals"]:
                    found[key] = rec

        # OCR.Space sometimes splits "John" and "44'" onto adjacent lines.
        for i, line in enumerate(lines):
            if scorer_rel._minute_count(line) > 0:
                continue
            hit = _unique_hit(line, rosters)
            if not hit:
                continue
            counts = []
            for d in (1, 2):
                for j in (i - d, i + d):
                    if 0 <= j < len(lines):
                        other = lines[j]
                        c = scorer_rel._minute_count(other)
                        if c <= 0:
                            continue
                        other_hit = _unique_hit(other, rosters)
                        if other_hit and other_hit != hit:
                            continue
                        counts.append(int(c))
            if counts:
                name, team = hit
                key = (league.norm(name), team)
                rec = {"player": name, "team": team, "goals": min(20, max(counts))}
                if key not in found or rec["goals"] > found[key]["goals"]:
                    found[key] = rec

        # Safe low-score fallback: for 1-0/0-1, one exact roster name on a page
        # containing a minute marker is enough to close the only goal.
        scoring = [team for team, n in expected.items() if n == 1]
        zeros = [team for team, n in expected.items() if n == 0]
        if len(scoring) == 1 and len(zeros) == 1:
            team = scoring[0]
            candidates = []
            for line in lines:
                hit = _unique_hit(line, {team: rosters.get(team, [])})
                if hit and hit[0] not in candidates:
                    candidates.append(hit[0])
            if len(candidates) == 1:
                name = candidates[0]
                found.setdefault(
                    (league.norm(name), team),
                    {"player": name, "team": team, "goals": 1},
                )

    scorers = list(found.values())
    totals = {home: 0, away: 0}
    for item in scorers:
        if item["team"] in totals:
            totals[item["team"]] += int(item["goals"])

    # ParsedText is only accepted when it closes the already validated score exactly.
    if totals != expected:
        return out

    old_total = 0
    for item in out.get("scorers") or []:
        try:
            old_total += int(item.get("goals") or 0)
        except Exception:
            pass
    new_total = sum(int(item["goals"]) for item in scorers)
    if new_total <= old_total:
        return out

    out["scorers"] = scorers
    out["scorers_confidence"] = max(float(out.get("scorers_confidence") or 0.0), 0.92)
    out["kind"] = "both"
    notes = str(out.get("notes") or "").strip()
    audit = "AJPA ParsedText scorers=" + ",".join(
        f'{x["player"]}@{x["team"]}x{int(x["goals"])}' for x in scorers
    )
    out["notes"] = (notes + (" | " if notes else "") + audit)[:1000]
    return out


def _payload(images, engine: str, guild_id: int | None):
    pages, texts = text_rescue._collect(images, engine)
    geometry = None
    try:
        geometry = text_rescue._geometry_payload(images, pages, guild_id, engine)
    except Exception as exc:
        print(f"WARNING AJPA OCRSPACE scorer ParsedText overlay Engine {engine}: {type(exc).__name__}: {exc}")
    plain = text_rescue._plain_payload(texts, guild_id, engine)
    result = text_rescue._merge(geometry, plain)
    if not result:
        raise RuntimeError("OCR.Space no produjo un payload utilizable")
    result = linked._repair_from_visible_links(result, texts, guild_id)
    return _recover(texts, guild_id, result)


bridge._payload_with_engine = _payload

print(
    "AJPA Liga: OCR.Space goleadores ParsedText ACTIVO | "
    "nombre+minuto validados por plantel y cierre exacto del marcador"
)
