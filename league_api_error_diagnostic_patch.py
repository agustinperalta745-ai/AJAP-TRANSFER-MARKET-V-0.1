"""Safe diagnostics for OpenAI API failures in AJAP Liga.

The Liga evidence handler intentionally catches all analysis exceptions so a bad
API call never crashes the Discord listener. Previously that also hid the useful
HTTP status and made every failure look identical. This patch keeps secrets out
of Discord while attaching a short actionable category (401/429/400/etc.) to
Staff review cards.
"""

from __future__ import annotations

import contextvars
import re

import league_automation_patch as league
import league_validation_admin_review_patch as strict


_LAST_API_ERROR = contextvars.ContextVar("ajap_last_api_error", default=None)
_ORIGINAL_ANALYZE = league.analyze
_ORIGINAL_SEND_REVIEW = strict._send_admin_review


def _safe_error(exc: Exception) -> str:
    """Return an actionable description without echoing credentials/body data."""
    text = str(exc or "")
    low = text.casefold()
    match = re.search(r"\bHTTP\s+(\d{3})\b", text, flags=re.I)
    status = int(match.group(1)) if match else None

    if status == 401 or "invalid_api_key" in low or "incorrect api key" in low:
        return "HTTP 401 — la API rechazó la clave (inválida, incompleta o del proyecto equivocado)."
    if status == 429 or "insufficient_quota" in low or "credit_balance_exhausted" in low:
        return "HTTP 429 — la cuenta/proyecto API no tiene saldo disponible o alcanzó un límite de uso."
    if status == 403:
        return "HTTP 403 — la clave existe pero no tiene permiso para usar ese recurso/modelo."
    if status == 404 or "model_not_found" in low:
        return "HTTP 404 — el modelo configurado no está disponible para este proyecto."
    if status == 400:
        return "HTTP 400 — OpenAI rechazó el formato de la solicitud o algún parámetro/modelo."
    if status is not None:
        return f"HTTP {status} — OpenAI rechazó la solicitud. Revisar billing/permisos/modelo."
    if "timed out" in low or "timeout" in low:
        return "Timeout — OpenAI no respondió dentro del tiempo esperado."
    if "json" in low:
        return "Respuesta inválida — OpenAI respondió, pero el bot no pudo interpretar el JSON devuelto."
    return f"{type(exc).__name__} — fallo durante el análisis de la captura."


async def _analyze_with_diagnostic(images):
    _LAST_API_ERROR.set(None)
    try:
        return await _ORIGINAL_ANALYZE(images)
    except Exception as exc:
        _LAST_API_ERROR.set(_safe_error(exc))
        raise


async def _send_review_with_diagnostic(message, reason: str, hashes=None):
    detail = _LAST_API_ERROR.get()
    if detail and str(reason).startswith("Ocurrió un error técnico"):
        reason = f"{reason}\n\n**Diagnóstico API:** {detail}"
        _LAST_API_ERROR.set(None)
    return await _ORIGINAL_SEND_REVIEW(message, reason, hashes)


if not getattr(league.analyze, "_ajap_api_error_diagnostic", False):
    _analyze_with_diagnostic._ajap_api_error_diagnostic = True
    league.analyze = _analyze_with_diagnostic

if not getattr(strict._send_admin_review, "_ajap_api_error_diagnostic", False):
    _send_review_with_diagnostic._ajap_api_error_diagnostic = True
    strict._send_admin_review = _send_review_with_diagnostic

print("AJAP Liga diagnóstico API activo: errores HTTP seguros visibles para Staff")

# Herramienta Staff para cargar/corregir goleadores de resultados ya persistidos,
# incluidos los partidos que fueron resueltos mediante carga manual.
import league_manual_scorers_patch  # noqa: F401,E402
