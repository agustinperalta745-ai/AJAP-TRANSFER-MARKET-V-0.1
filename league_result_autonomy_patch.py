"""Keep clear PES6 results automatic even when scorer OCR is uncertain.

Problem fixed:
The evidence reader exposed one global confidence for score + teams + scorers.
When player names were hard to read, that global confidence dropped below the
Liga threshold and a perfectly readable result was incorrectly sent to Staff.

This late patch separates the two concerns without changing persisted data:
- main mixed vision still runs first;
- if the score is missing/low-confidence, a second result-only pass validates
  teams, score and final/partial state independently;
- scorer uncertainty never lowers result confidence;
- low-confidence scorer rows are not persisted;
- if the result is solid but scorers are weak/missing, the existing dedicated
  scorer-detail reader gets one independent chance to recover visible names.

The official result remains conservative: Staff review still wins when the
result-only pass cannot reach the configured league confidence threshold.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request

import league_automation_patch as league
import league_openai_retry_patch as retry
import league_scorer_continuation_rows_patch as scorer_detail


SCORER_MIN_CONFIDENCE = 0.72


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _result_only_vision_sync(images):
    api_key = league.os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY")

    prompt = """Sos un verificador de RESULTADOS FINALES/PARCIALES de PES 6.
Analizá TODAS las imágenes del mensaje, pero IGNORÁ por completo los nombres de goleadores.
Tu única tarea es leer equipos, marcador y si la captura demuestra final/partial/unknown.

Devolvé SOLAMENTE JSON válido, sin markdown:
{"kind":"result|unknown","match_state":"final|partial|unknown","home_team":"","away_team":"","home_goals":null,"away_goals":null,"result_confidence":0.0,"notes":""}

Reglas:
- result_confidence mide EXCLUSIVAMENTE la certeza de equipos + marcador, no goleadores.
- No bajes result_confidence porque un nombre de jugador sea ilegible: los jugadores no forman parte de esta lectura.
- match_state=final solo con evidencia visual clara de fin/post-partido/resultado final.
- match_state=partial si hay evidencia clara de entretiempo, pausa o partido todavía en curso.
- match_state=unknown si el marcador se lee pero no se puede demostrar si terminó.
- No inventes equipos ni goles.
- Los nombres de equipos válidos son exactamente: """ + ", ".join(league.TEAMS)

    content = [{"type": "input_text", "text": prompt}]
    for data, mime in images:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}",
                "detail": "high",
            }
        )

    body = json.dumps(
        {
            "model": league.MODEL,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": 650,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        league.API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=75) as res:
            response = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"OpenAI result-only HTTP {exc.code}: {detail}") from exc

    text = league.response_text(response)
    if not text:
        raise RuntimeError("La lectura solo-resultado no devolvió texto")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("La lectura solo-resultado no devolvió JSON")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise RuntimeError("La lectura solo-resultado devolvió un formato inválido")
    return parsed


def _merge_result_only(primary, result_only):
    primary = dict(primary or {})
    if not isinstance(result_only, dict):
        return primary

    candidate = {
        "kind": "result",
        "home_team": result_only.get("home_team"),
        "away_team": result_only.get("away_team"),
        "home_goals": result_only.get("home_goals"),
        "away_goals": result_only.get("away_goals"),
    }
    score = league.parsed_score(candidate)
    confidence = _float(result_only.get("result_confidence"), 0.0)
    if not score or confidence < league.MIN_CONF:
        return primary

    home, away, hg, ag = score
    primary["home_team"] = home
    primary["away_team"] = away
    primary["home_goals"] = int(hg)
    primary["away_goals"] = int(ag)
    primary["match_state"] = str(result_only.get("match_state") or "unknown").casefold()
    primary["result_confidence"] = confidence
    primary["confidence"] = confidence
    scorers = [x for x in (primary.get("scorers") or []) if isinstance(x, dict)]
    primary["kind"] = "both" if scorers else "result"
    notes = str(primary.get("notes") or "").strip()
    audit = f"AJAP result-only rescue confidence={confidence:.2f}"
    primary["notes"] = (notes + (" | " if notes else "") + audit)[:1000]
    return primary


def _score_is_confident(payload):
    return bool(
        isinstance(payload, dict)
        and league.parsed_score(payload)
        and _float(payload.get("result_confidence", payload.get("confidence")), 0.0)
        >= league.MIN_CONF
    )


def _scorer_confidence(payload):
    if not isinstance(payload, dict):
        return 0.0
    if payload.get("scorer_repair_confidence") is not None:
        return _float(payload.get("scorer_repair_confidence"), 0.0)
    if payload.get("scorers_confidence") is not None:
        return _float(payload.get("scorers_confidence"), 0.0)
    if payload.get("scorers"):
        return _float(payload.get("confidence"), 0.0)
    return 0.0


_BASE_ANALYZE = league.analyze


async def analyze_with_independent_result_confidence(images):
    primary = None
    primary_error = None
    try:
        primary = await _BASE_ANALYZE(images)
    except Exception as exc:
        primary_error = exc
        print(
            f"WARNING AJAP lectura mixta falló; intento solo-resultado: "
            f"{type(exc).__name__}: {exc}"
        )

    if not isinstance(primary, dict):
        primary = {}

    # Preserve a scorer-specific confidence BEFORE replacing the global value
    # with result confidence.
    if "scorers_confidence" not in primary:
        primary["scorers_confidence"] = _scorer_confidence(primary)

    if league.parsed_score(primary):
        current_result_conf = _float(
            primary.get("result_confidence", primary.get("confidence")), 0.0
        )
        if current_result_conf >= league.MIN_CONF:
            primary["result_confidence"] = current_result_conf
            primary["confidence"] = current_result_conf
        else:
            try:
                result_only = await league.asyncio.to_thread(
                    retry._call_with_retry,
                    _result_only_vision_sync,
                    "lectura solo-resultado",
                    images,
                )
                primary = _merge_result_only(primary, result_only)
            except Exception as exc:
                print(
                    f"WARNING AJAP rescate solo-resultado falló: "
                    f"{type(exc).__name__}: {exc}"
                )
    else:
        try:
            result_only = await league.asyncio.to_thread(
                retry._call_with_retry,
                _result_only_vision_sync,
                "lectura solo-resultado",
                images,
            )
            primary = _merge_result_only(primary, result_only)
        except Exception as exc:
            print(
                f"WARNING AJAP rescate solo-resultado falló: "
                f"{type(exc).__name__}: {exc}"
            )
            if primary_error is not None:
                raise primary_error

    # If the result is solid but the scorer read is weak/missing, give the
    # dedicated scorer reader one independent attempt. It may enrich names but
    # can never modify the official score.
    if _score_is_confident(primary) and (
        not primary.get("scorers")
        or _scorer_confidence(primary) < SCORER_MIN_CONFIDENCE
    ):
        try:
            scorer_base = dict(primary)
            scorer_base["scorers"] = []
            scorer_base["kind"] = "result"
            repair = await league.asyncio.to_thread(
                scorer_detail._repair_vision_sync,
                images,
                scorer_base,
            )
            recovered = scorer_detail._merge_repair(scorer_base, repair)
            if recovered.get("scorers"):
                # Keep the independently validated result fields and only take
                # named scorer evidence from the scorer-specific pass.
                primary["scorers"] = recovered.get("scorers") or []
                primary["kind"] = "both"
                primary["scorer_detail_repair"] = True
                primary["scorer_repair_confidence"] = _float(
                    recovered.get("scorer_repair_confidence"), 0.0
                )
                primary["scorers_confidence"] = primary["scorer_repair_confidence"]
                if "unnamed_home" in recovered:
                    primary["unnamed_home"] = recovered["unnamed_home"]
                if "unnamed_away" in recovered:
                    primary["unnamed_away"] = recovered["unnamed_away"]
        except Exception as exc:
            # A scorer failure is never a reason to reject a clear result.
            print(
                f"WARNING AJAP lectura independiente de goleadores falló: "
                f"{type(exc).__name__}: {exc}"
            )

    if _score_is_confident(primary):
        primary["confidence"] = _float(primary.get("result_confidence"), 0.0)
    return primary


_BASE_PARSED_SCORERS = league.parsed_scorers


def parsed_scorers_with_independent_confidence(runtime, guild_id, payload):
    if not isinstance(payload, dict):
        return []
    confidence = _scorer_confidence(payload)
    if confidence < SCORER_MIN_CONFIDENCE:
        return []
    return _BASE_PARSED_SCORERS(runtime, guild_id, payload)


if not getattr(league.analyze, "_ajap_result_autonomy", False):
    analyze_with_independent_result_confidence._ajap_result_autonomy = True
    analyze_with_independent_result_confidence._ajap_result_autonomy_base = _BASE_ANALYZE
    league.analyze = analyze_with_independent_result_confidence

if not getattr(league.parsed_scorers, "_ajap_independent_scorer_confidence", False):
    parsed_scorers_with_independent_confidence._ajap_independent_scorer_confidence = True
    parsed_scorers_with_independent_confidence._ajap_independent_scorer_confidence_base = _BASE_PARSED_SCORERS
    league.parsed_scorers = parsed_scorers_with_independent_confidence

print(
    "AJAP Liga: confianza de resultado separada de goleadores + rescate solo-resultado activo"
)
