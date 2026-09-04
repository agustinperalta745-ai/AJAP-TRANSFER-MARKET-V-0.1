"""Plain-text rescue for OCR.Space PES6 result screens.

OCR.Space can correctly read the visible text while its overlay/geometry is too
weak for AJPA's positional parser. This layer consumes ParsedText as a second,
independent signal. It is deliberately conservative:

- final state is accepted only with PES post-match menu markers;
- the strongest score rescue sums the visible 1er/2do period rows;
- teams must resolve against AJPA's official PES/team aliases;
- scorer names still require the positional + roster-validated parser;
- any disagreement between two confident score reads is forced to Staff.

This fixes clear result screens such as Man Blue 2-1 Fiorentina without making
up missing scorer data. If scorers are not present/complete, the existing Staff
fallback remains authoritative.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import league_automation_patch as league
import league_local_ocr_patch as local
import league_ocrspace_result_bridge_patch as bridge
import pes_username_link_patch as pes_links


def _request_full(data: bytes, engine: str):
    api_key = (os.getenv("OCR_SPACE_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Falta OCR_SPACE_API_KEY")

    blob, width, height = bridge._compress_for_free_api(data)
    form = {
        "base64Image": "data:image/jpeg;base64," + base64.b64encode(blob).decode("ascii"),
        "language": "auto",
        "isOverlayRequired": "true",
        "detectOrientation": "true",
        "scale": "true",
        "isTable": "true",
        "OCREngine": str(engine),
    }
    body = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        bridge.API_URL,
        data=body,
        headers={
            "apikey": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"OCR.Space HTTP {exc.code}: {detail}") from exc

    if bool(payload.get("IsErroredOnProcessing")):
        raise RuntimeError(
            "OCR.Space: "
            + str(payload.get("ErrorMessage") or payload.get("ErrorDetails") or "error de procesamiento")[:500]
        )

    parsed = payload.get("ParsedResults")
    if not isinstance(parsed, list) or not parsed:
        raise RuntimeError("OCR.Space no devolvió resultados")

    pages = []
    texts = []
    for result in parsed:
        if not isinstance(result, dict):
            continue
        try:
            exit_code = int(result.get("FileParseExitCode"))
        except Exception:
            exit_code = 0
        if exit_code != 1:
            continue

        text = str(result.get("ParsedText") or "").strip()
        if text:
            texts.append(text)

        rows = bridge._overlay_rows(result, width, height, engine)
        if rows:
            pages.append(rows)

    if not pages and not texts:
        raise RuntimeError("OCR.Space no devolvió texto utilizable")
    return pages, texts


def _collect(images, engine: str):
    pages = []
    texts = []
    errors = []
    for data, _mime in images:
        try:
            p, t = _request_full(data, engine)
            pages.extend(p)
            texts.extend(t)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    if pages or texts:
        return pages, texts
    raise RuntimeError(" | ".join(errors) if errors else "OCR.Space no pudo leer las imágenes")


def _with_guild_context(guild_id):
    try:
        return pes_links._RESULT_GUILD_ID.set(int(guild_id)) if guild_id is not None else None
    except Exception:
        return None


def _reset_guild_context(token):
    if token is None:
        return
    try:
        pes_links._RESULT_GUILD_ID.reset(token)
    except Exception:
        pass


def _geometry_payload(images, pages, guild_id, engine):
    if not pages:
        return None
    original = local._all_items
    token = _with_guild_context(guild_id)
    try:
        local._all_items = lambda _imgs: pages
        payload = local._local_payload(images)
    finally:
        local._all_items = original
        _reset_guild_context(token)

    payload = dict(payload or {})
    payload["source_kind"] = "ocrspace"
    payload["ocr_engine"] = str(engine)
    payload["notes"] = f"OCR.Space Engine {engine} overlay"
    return payload


def _team_pair_from_text(text: str):
    full = league.norm(text)
    if not full:
        return None

    hits = {}
    try:
        variants = local._team_variants()
    except Exception:
        variants = [(team, team) for team in league.TEAMS]

    for variant, team in variants:
        key = league.norm(variant)
        if len(key) < 3:
            continue
        pos = full.find(key)
        if pos < 0:
            continue
        canonical = league.canonical_team(team) or str(team)
        current = hits.get(canonical)
        candidate = (pos, len(key))
        if current is None or candidate[0] < current[0] or (
            candidate[0] == current[0] and candidate[1] > current[1]
        ):
            hits[canonical] = candidate

    if len(hits) < 2:
        return None

    ranked = sorted(
        ((pos, -length, team) for team, (pos, length) in hits.items()),
        key=lambda item: (item[0], item[1]),
    )
    first = ranked[0][2]
    second = next((item[2] for item in ranked[1:] if item[2] != first), None)
    if not second:
        return None
    return first, second


def _state_from_text(text: str):
    key = league.norm(text)
    partial = (
        "entretiempo",
        "medio tiempo",
        "half time",
        "primer tiempo",
    )
    final = (
        "terminar juego",
        "jugar otro partido",
        "detalles del partido",
        "pasar a selec de equipo",
        "pasar a selec",
        "resultado final",
        "fin del partido",
    )
    if any(marker in key for marker in final):
        return "final"
    if any(marker in key for marker in partial):
        return "partial"
    return "unknown"


def _nearest_period_pair(line: str, marker_patterns):
    key = league.norm(line)
    for pattern in marker_patterns:
        match = re.search(pattern, key, re.I)
        if not match:
            continue
        before = re.findall(r"(?<!\d)(\d{1,2})(?!\d)", key[: match.start()])
        after = re.findall(r"(?<!\d)(\d{1,2})(?!\d)", key[match.end() :])
        if before and after:
            left, right = int(before[-1]), int(after[0])
            if 0 <= left <= 20 and 0 <= right <= 20:
                return left, right
    return None


def _period_score(text: str):
    first = None
    second = None
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]

    first_patterns = (
        r"\b1er\b",
        r"\b1ro\b",
        r"\bprimer(?:o)?(?:\s+tiempo)?\b",
    )
    second_patterns = (
        r"\b2do\b",
        r"\b2(?:do|ro)?\b(?=\s*(?:tiempo)\b)",
        r"\bsegundo(?:\s+tiempo)?\b",
    )

    for line in lines:
        if first is None:
            first = _nearest_period_pair(line, first_patterns)
        if second is None:
            second = _nearest_period_pair(line, second_patterns)

    # Some OCR responses flatten the whole table onto one line. Retry against
    # the complete text only if a period row was not recovered line-by-line.
    flat = " ".join(lines)
    if first is None:
        first = _nearest_period_pair(flat, first_patterns)
    if second is None:
        second = _nearest_period_pair(flat, second_patterns)

    if first is None or second is None:
        return None
    return first[0] + second[0], first[1] + second[1]


def _explicit_score(text: str):
    # Only separators that visibly represent a score. Do not infer from arbitrary
    # adjacent numbers because PES screens also contain category/points values.
    for line in str(text or "").splitlines():
        match = re.search(r"(?<!\d)(\d{1,2})\s*[-:–—]\s*(\d{1,2})(?!\d)", line)
        if not match:
            continue
        left, right = int(match.group(1)), int(match.group(2))
        if 0 <= left <= 20 and 0 <= right <= 20:
            return left, right
    return None


def _plain_payload(texts, guild_id, engine):
    text = "\n".join(str(item or "") for item in texts if str(item or "").strip())
    pair = _team_pair_from_text(text)
    state = _state_from_text(text)
    score = _period_score(text) or _explicit_score(text)

    payload = {
        "kind": "unknown",
        "match_state": state,
        "home_team": pair[0] if pair else "",
        "away_team": pair[1] if pair else "",
        "home_goals": score[0] if score else None,
        "away_goals": score[1] if score else None,
        "scorers": [],
        "confidence": 0.0,
        "result_confidence": 0.0,
        "scorers_confidence": 0.0,
        "source_kind": "ocrspace",
        "ocr_engine": str(engine),
        "notes": f"OCR.Space Engine {engine} ParsedText rescue",
    }

    if pair and score:
        token = _with_guild_context(guild_id)
        try:
            try:
                payload = pes_links._resolve_payload_with_links(pes_links.APP, guild_id, payload)
            except Exception:
                pass
        finally:
            _reset_guild_context(token)

        probe = dict(payload)
        probe["kind"] = "result"
        if league.parsed_score(probe):
            payload["kind"] = "result"
            # Period-row arithmetic is strong evidence on a PES result screen.
            # State remains independently checked so a halftime screen is never
            # turned into a final merely because two numbers were present.
            confidence = 0.95 if _period_score(text) else 0.89
            payload["confidence"] = confidence
            payload["result_confidence"] = confidence
    return payload


def _result_tuple(payload):
    if not isinstance(payload, dict):
        return None
    return league.parsed_score(payload)


def _same_result(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    return a[0] == b[1] and a[1] == b[0] and int(a[2]) == int(b[3]) and int(a[3]) == int(b[2])


def _merge(geometry, plain):
    if not geometry:
        return dict(plain or {})
    if not plain:
        return dict(geometry or {})

    out = dict(geometry)
    g_score = _result_tuple(geometry)
    p_score = _result_tuple(plain)

    if g_score and p_score and not _same_result(g_score, p_score):
        out["kind"] = "unknown"
        out["match_state"] = "unknown"
        out["confidence"] = 0.0
        out["result_confidence"] = 0.0
        out["notes"] = (
            f"{geometry.get('notes', '')} | {plain.get('notes', '')} | "
            f"CONFLICTO OCR: overlay={g_score}, texto={p_score}"
        ).strip(" |")
        return out

    if not g_score and p_score:
        for field in (
            "kind",
            "home_team",
            "away_team",
            "home_goals",
            "away_goals",
            "confidence",
            "result_confidence",
        ):
            out[field] = plain.get(field)

    g_state = str(geometry.get("match_state") or "unknown").casefold()
    p_state = str(plain.get("match_state") or "unknown").casefold()
    if g_state == "unknown" and p_state in {"final", "partial"}:
        out["match_state"] = p_state

    # Preserve positional, roster-validated scorers from the overlay parser.
    if geometry.get("scorers"):
        out["scorers"] = geometry.get("scorers")
        if _result_tuple(out):
            out["kind"] = "both"

    out["source_kind"] = "ocrspace"
    out["notes"] = (
        f"{geometry.get('notes', '')} | {plain.get('notes', '')}"
    ).strip(" |")
    return out


def _payload_with_text_rescue(images, engine: str, guild_id: int | None):
    pages, texts = _collect(images, engine)
    geometry = None
    try:
        geometry = _geometry_payload(images, pages, guild_id, engine)
    except Exception as exc:
        print(
            f"WARNING AJPA OCRSPACE overlay parser Engine {engine}: "
            f"{type(exc).__name__}: {exc}"
        )

    plain = _plain_payload(texts, guild_id, engine)
    result = _merge(geometry, plain)
    if not result:
        raise RuntimeError("OCR.Space no produjo un payload utilizable")
    return result


# bridge._analyze calls this global on every request, including after reconnects.
# Replacing it here makes both Engine 2 and Engine 3 use ParsedText rescue without
# changing the persistence/Staff safety pipeline.
bridge._payload_with_engine = _payload_with_text_rescue

print(
    "AJPA Liga: OCR.Space ParsedText rescue ACTIVO | "
    "resultado por 1er/2do + menú final, goleadores siguen roster-validados"
)
