"""Keep a validated OCR.Space result official when only scorer attribution is incomplete.

This is intentionally a late, narrow fallback. It does not change OCR, team/score
validation, or the normal complete-scorer path. When OCR.Space already proved a
FINAL score but roster validation cannot close every scorer, AJAP:

1. persists the official result (and any scorer already validated safely),
2. refreshes standings/app and publishes the normal result-to-load card,
3. creates the existing Staff "GOLEADORES PENDIENTES" card with Agregar goleador,
4. never asks Staff to re-enter the score that was already validated.
"""
from __future__ import annotations

import league_automation_patch as league
import league_ocrspace_result_bridge_patch as bridge
import league_result_evidence_patch as evidence
import league_ges_result_queue_patch as ges
import league_scorer_pending_patch as scorer_pending


_BASE_SEND_STAFF_REVIEW = bridge._send_staff_review
_SCORER_REASON = "no pudo cerrar todos los goleadores contra las plantillas"


def _eligible(payload, reason):
    if _SCORER_REASON not in str(reason or "").casefold():
        return False
    if not isinstance(payload, dict):
        return False
    score = bridge._score(payload)
    if not score:
        return False
    if str(payload.get("match_state") or "unknown").casefold() != "final":
        return False
    try:
        confidence = float(payload.get("result_confidence") or payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return False
    return confidence >= bridge.MIN_CONF


async def _result_official_scorers_pending(message, reason, hashes, payload):
    runtime = bridge.APP
    bot = bridge.BOT
    if runtime is None or bot is None or not getattr(message, "guild", None):
        return False

    score = bridge._score(payload)
    if not score:
        return False
    home, away, hg, ag = score

    # Keep only scorer entries that already passed the same strict roster check as
    # the normal automatic path. Missing goals remain empty for Staff to assign.
    scorers = bridge._clean_scorers(runtime, message.guild.id, payload, score)
    try:
        confidence = float(payload.get("result_confidence") or payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    clean_payload = dict(payload)
    clean_payload.update(
        {
            "kind": "both" if scorers else "result",
            "match_state": "final",
            "home_team": home,
            "away_team": away,
            "home_goals": int(hg),
            "away_goals": int(ag),
            "scorers": scorers,
            "source_kind": "ocrspace",
            "confidence": confidence,
        }
    )
    notes = str(clean_payload.get("notes") or "").strip()
    audit = "resultado oficial; goleadores incompletos enviados a Staff"
    clean_payload["notes"] = (notes + (" | " if notes else "") + audit)[:1000]

    evidence._stage(
        runtime,
        message,
        score,
        clean_payload,
        hashes,
        "OCRSPACE_GOLEADORES_PENDIENTES",
    )
    row = evidence._row(
        runtime,
        message.guild.id,
        source_message_id=message.id,
    )
    if row is None:
        raise RuntimeError("No se pudo recuperar el resultado validado")

    ok, result_state, duplicate, _scorer_count = evidence._persist_official(
        runtime,
        message.guild.id,
        row,
        include_scorers=bool(scorers),
        status="FINAL_CARGADO_GOLEADORES_PENDIENTES",
    )

    if not ok and result_state == "DUPLICADO":
        await bridge._safe_reply(
            message,
            "ℹ️ El cruce ya tiene un resultado oficial cargado. No dupliqué el partido ni los puntos.",
        )
        return True
    if not ok:
        raise RuntimeError(f"No se pudo persistir resultado: {result_state}")

    try:
        await league.refresh(runtime, bot, message.guild.id)
    except Exception as exc:
        print(f"WARNING AJPA OCRSPACE SCORER-PENDING REFRESH: {type(exc).__name__}: {exc}")

    try:
        await ges._send(runtime, message.guild.id, row, home, away, hg, ag)
    except Exception as exc:
        print(f"WARNING AJPA OCRSPACE SCORER-PENDING GES: {type(exc).__name__}: {exc}")

    await bridge._react(message, "✅")

    # Reuse the established Staff workflow: it shows the already-official score,
    # exact missing goal counts and the persistent "Agregar goleador" button.
    await scorer_pending._ensure_card(runtime, bot, message)
    return True


async def _send_staff_review_scorer_only(message, reason, hashes=None, payload=None):
    if not _eligible(payload, reason):
        return await _BASE_SEND_STAFF_REVIEW(message, reason, hashes, payload)

    try:
        handled = await _result_official_scorers_pending(
            message,
            reason,
            hashes or [],
            dict(payload or {}),
        )
        if handled:
            return True
    except Exception as exc:
        # Safety first: if this narrow fallback itself fails, preserve the old
        # Staff review behavior instead of risking a silent/half-finished result.
        print(
            f"WARNING AJPA OCRSPACE SCORER-ONLY FALLBACK source={getattr(message, 'id', '?')}: "
            f"{type(exc).__name__}: {exc}"
        )

    return await _BASE_SEND_STAFF_REVIEW(message, reason, hashes, payload)


bridge._send_staff_review = _send_staff_review_scorer_only

print(
    "AJPA Liga: fallback scorer-only ACTIVO | resultado final validado se carga y "
    "solo los goleadores faltantes pasan a Staff"
)
