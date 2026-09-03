"""Reliability patch for transient OpenAI vision failures in AJAP Liga.

What this fixes:
- HTTP 429 by itself is NOT treated as proof that billing credit is exhausted.
- Transient 429/5xx/timeout failures are retried automatically.
- The dedicated PES6 scorer-detail pass gets the same retry protection, so a
  temporary API refusal does not silently turn clearly visible scorers into
  "sin goleador identificado" after a single failed request.

Hard quota/billing errors such as `insufficient_quota` are intentionally not
retried because waiting a few seconds cannot resolve them.
"""

from __future__ import annotations

import time

import league_api_error_diagnostic_patch as diagnostic
import league_automation_patch as league
import league_scorer_continuation_rows_patch as scorer_detail


_RETRY_DELAYS = (2.0, 5.0, 9.0)
_HARD_QUOTA_MARKERS = (
    "insufficient_quota",
    "credit_balance_exhausted",
    "billing_hard_limit_reached",
    "billing_not_active",
)
_TRANSIENT_MARKERS = (
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "timeout",
    "timed out",
    "temporarily unavailable",
    "connection reset",
)


def _is_hard_quota(exc: Exception) -> bool:
    text = str(exc or "").casefold()
    return any(marker in text for marker in _HARD_QUOTA_MARKERS)


def _is_transient(exc: Exception) -> bool:
    if _is_hard_quota(exc):
        return False
    text = str(exc or "").casefold()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _call_with_retry(fn, label: str, *args):
    attempt = 0
    while True:
        try:
            return fn(*args)
        except Exception as exc:
            if not _is_transient(exc) or attempt >= len(_RETRY_DELAYS):
                raise
            delay = _RETRY_DELAYS[attempt]
            attempt += 1
            print(
                f"AJAP Liga OpenAI retry: {label} intento={attempt + 1} "
                f"en {delay:.0f}s por {type(exc).__name__}: {exc}"
            )
            time.sleep(delay)


# ---------------------------------------------------------------------------
# Correct the Staff-facing 429 diagnosis. The previous wording grouped every
# 429 together with exhausted credit, which is not technically correct.
# ---------------------------------------------------------------------------
def _safe_error_precise(exc: Exception) -> str:
    text = str(exc or "")
    low = text.casefold()

    if "http 401" in low or "invalid_api_key" in low or "incorrect api key" in low:
        return "HTTP 401 — la API rechazó la clave (inválida, incompleta o del proyecto equivocado)."
    if any(marker in low for marker in _HARD_QUOTA_MARKERS):
        return "HTTP 429 — la cuota/crédito disponible del proyecto API está agotada o bloqueada."
    if "http 429" in low:
        return (
            "HTTP 429 — OpenAI rechazó temporalmente la solicitud por un límite de uso/velocidad. "
            "Ese código por sí solo NO significa que falte saldo; AJAP reintenta automáticamente."
        )
    if "http 403" in low:
        return "HTTP 403 — la clave existe pero no tiene permiso para usar ese recurso/modelo."
    if "http 404" in low or "model_not_found" in low:
        return "HTTP 404 — el modelo configurado no está disponible para este proyecto."
    if "http 400" in low:
        return "HTTP 400 — OpenAI rechazó el formato de la solicitud o algún parámetro/modelo."
    if "http 500" in low or "http 502" in low or "http 503" in low or "http 504" in low:
        return "OpenAI tuvo un error temporal del servidor; AJAP reintenta automáticamente."
    if "timed out" in low or "timeout" in low:
        return "Timeout — OpenAI no respondió dentro del tiempo esperado; AJAP reintenta automáticamente."
    if "json" in low:
        return "Respuesta inválida — OpenAI respondió, pero el bot no pudo interpretar el JSON devuelto."
    return f"{type(exc).__name__} — fallo durante el análisis de la captura."


diagnostic._safe_error = _safe_error_precise


# ---------------------------------------------------------------------------
# Main result/scorer vision call.
# ---------------------------------------------------------------------------
if not getattr(league.vision_sync, "_ajap_openai_retry", False):
    _BASE_VISION_SYNC = league.vision_sync

    def _vision_sync_with_retry(images):
        return _call_with_retry(_BASE_VISION_SYNC, "lectura principal", images)

    _vision_sync_with_retry._ajap_openai_retry = True
    _vision_sync_with_retry._ajap_openai_retry_base = _BASE_VISION_SYNC
    league.vision_sync = _vision_sync_with_retry


# ---------------------------------------------------------------------------
# Focused PES6 scorer-detail call. The installed analyze wrapper resolves this
# module function at runtime, so replacing it here protects future captures.
# ---------------------------------------------------------------------------
if not getattr(scorer_detail._repair_vision_sync, "_ajap_openai_retry", False):
    _BASE_SCORER_REPAIR = scorer_detail._repair_vision_sync

    def _scorer_repair_with_retry(images, payload):
        return _call_with_retry(
            _BASE_SCORER_REPAIR,
            "lectura de goleadores",
            images,
            payload,
        )

    _scorer_repair_with_retry._ajap_openai_retry = True
    _scorer_repair_with_retry._ajap_openai_retry_base = _BASE_SCORER_REPAIR
    scorer_detail._repair_vision_sync = _scorer_repair_with_retry


print(
    "AJAP Liga OpenAI reliability: 429 temporal + 5xx + timeout con reintentos; "
    "429 ya no se diagnostica automáticamente como falta de saldo"
)
