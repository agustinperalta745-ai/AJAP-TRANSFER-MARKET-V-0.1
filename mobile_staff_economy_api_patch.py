"""Operational Staff economy endpoint for AJPA Mobile.

Exposes the same audited balance adjustment used by Discord Administration ->
Economia. Only a paired Staff session can use it. The mutation runs inside the
configured guild context and delegates to admin_finance_patch.adjust_balance,
so club_finances and finance_adjustments stay identical between Discord and APK.
"""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlparse

import admin_finance_patch
import guild_isolation_patch
import mobile_read_api
import mobile_staff_api_patch
import mobile_write_api


def _canonical_club(runtime, requested: str) -> str:
    raw = str(requested or "").strip()
    if not raw:
        raise mobile_write_api.ApiFailure("Elegí un equipo.")
    clubs = admin_finance_patch.roster_clubs(runtime)
    for club in clubs:
        if str(club).casefold() == raw.casefold():
            return str(club)
    raise mobile_write_api.ApiFailure("Ese equipo no existe en el plantel activo.", HTTPStatus.NOT_FOUND)


def _perform_adjustment(payload: dict, staff_id: int) -> dict:
    mode = str(payload.get("mode") or "").strip().upper()
    if mode not in {"ADD", "REMOVE"}:
        raise mobile_write_api.ApiFailure("Tipo de ajuste economico invalido.")

    raw_amount = payload.get("amount")
    try:
        amount = int(raw_amount)
    except (TypeError, ValueError):
        raise mobile_write_api.ApiFailure("Escribi un monto valido mayor a cero.")
    if amount <= 0:
        raise mobile_write_api.ApiFailure("El monto debe ser mayor a cero.")

    runtime = admin_finance_patch.APP
    if runtime is None:
        # staff_admin is guaranteed to use the final runtime once Discord patches
        # finish loading, and provides the same db/es_admin/price helpers.
        import staff_admin_organized_patch as staff_admin
        runtime = staff_admin.APP
    if runtime is None:
        raise mobile_write_api.ApiFailure(
            "AJPA todavia esta terminando de iniciar. Intenta nuevamente en unos segundos.",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )

    with guild_isolation_patch.guild_context(mobile_staff_api_patch._mobile_guild_id()):
        club = _canonical_club(runtime, payload.get("club"))
        ok, result = admin_finance_patch.adjust_balance(runtime, club, amount, mode, int(staff_id))
        if not ok:
            # Discord formatting uses **bold**. Keep the same message but clean it
            # for a native mobile alert.
            raise mobile_write_api.ApiFailure(str(result or "No se pudo ajustar el presupuesto.").replace("**", ""))
        before, after, delta = result
        return {
            "ok": True,
            "club": club,
            "mode": mode,
            "amount": amount,
            "delta": int(delta),
            "balance_before": int(before),
            "balance_after": int(after),
        }


def apply_mobile_staff_economy_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_staff_economy_api_patch", False):
        return

    original_post = handler.do_POST

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/admin/economy/adjust":
            return original_post(self)
        try:
            payload = mobile_write_api._read_json(self)
            with mobile_write_api.write_db() as conn:
                mobile_write_api.ensure_schema(conn)
                session = mobile_staff_api_patch._staff_session(self.headers, conn)
            result = _perform_adjustment(payload, int(session["user_id"]))
            self._json(result)
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            print(f"AJPA mobile Staff economy POST error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudo ajustar el presupuesto."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_staff_economy_api_patch = True
    print("AJPA Mobile: Staff economy audited adjustments enabled")
