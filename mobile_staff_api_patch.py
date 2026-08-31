"""Operational Staff endpoints for AJPA Mobile.

Exposes the three Staff actions that already exist in Discord:
- review/approve/reject/mark PES for accepted market operations;
- review/approve/reject clausulazo requests;
- safely undo an already applied transfer.

Every route requires the paired mobile session to be Staff and runs inside the
configured mobile guild context so it mutates the exact same SQLite database as
Discord.
"""

from __future__ import annotations

import os
import re
from http import HTTPStatus
from urllib.parse import urlparse

import guild_isolation_patch
import mobile_read_api
import mobile_write_api


def _mobile_guild_id() -> int:
    raw = (
        os.getenv("AJPA_MOBILE_GUILD_ID")
        or os.getenv("DISCORD_GUILD_ID")
        or ""
    ).strip()
    if not raw.isdigit():
        raise mobile_write_api.ApiFailure(
            "AJPA Mobile no tiene un servidor de Discord configurado.",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
    return int(raw)


def _staff_session(headers, conn):
    session = mobile_write_api._session(headers, conn)
    if not session.get("is_staff"):
        raise mobile_write_api.ApiFailure(
            "Esta herramienta es exclusiva para Staff.",
            HTTPStatus.FORBIDDEN,
        )
    return session


def _tables(conn):
    return {
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _columns(conn, table: str):
    if table not in _tables(conn):
        return set()
    return {
        str(row["name"])
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def _deal_rows(conn, transfer_id: int):
    row = conn.execute(
        "SELECT * FROM transfers WHERE id=? LIMIT 1", (int(transfer_id),)
    ).fetchone()
    if not row:
        return []
    keys = set(row.keys())
    group = row["deal_group"] if "deal_group" in keys else None
    if group:
        return conn.execute(
            "SELECT * FROM transfers WHERE deal_group=? ORDER BY id ASC", (group,)
        ).fetchall()
    return [row]


def operations_payload(conn):
    if "transfers" not in _tables(conn):
        return {"items": []}
    cols = _columns(conn, "transfers")
    rows = conn.execute(
        """
        SELECT * FROM transfers
        WHERE UPPER(COALESCE(status,'')) IN ('PENDIENTE_ADMIN','APROBADA')
        ORDER BY id ASC
        LIMIT 200
        """
    ).fetchall()
    grouped = {}
    for row in rows:
        keys = set(row.keys())
        group = row["deal_group"] if "deal_group" in keys and row["deal_group"] else None
        key = f"G:{group}" if group else f"O:{row['id']}"
        grouped.setdefault(key, []).append(row)

    items = []
    for rows_for_deal in grouped.values():
        first = rows_for_deal[0]
        statuses = {str(row["status"] or "").upper() for row in rows_for_deal}
        status = next(iter(statuses)) if len(statuses) == 1 else "MIXTO"
        items.append(
            {
                "id": int(first["id"]),
                "status": status,
                "operation_type": str(first["operation_type"] or "TRANSFERENCIA") if "operation_type" in cols else "TRANSFERENCIA",
                "seller": str(first["seller"] or ""),
                "buyer": str(first["buyer"] or ""),
                "amount": str(first["amount"] or "$0"),
                "players": [str(row["player"] or "") for row in rows_for_deal],
                "rows": [int(row["id"]) for row in rows_for_deal],
            }
        )
    items.sort(key=lambda item: item["id"])
    return {"items": items}


def clauses_payload(conn):
    if "clause_requests" not in _tables(conn):
        return {"items": []}
    rows = conn.execute(
        """
        SELECT * FROM clause_requests
        WHERE UPPER(COALESCE(status,''))='PENDIENTE_STAFF'
        ORDER BY id ASC
        LIMIT 100
        """
    ).fetchall()
    return {
        "items": [
            {
                "id": int(row["id"]),
                "player": str(row["player"] or ""),
                "seller_club": str(row["seller_club"] or ""),
                "buyer_club": str(row["buyer_club"] or ""),
                "buyer_username": str(row["buyer_username"] or ""),
                "amount": int(row["amount"] or 0),
                "status": str(row["status"] or ""),
                "requested_at": str(row["requested_at"] or ""),
            }
            for row in rows
        ]
    }


def reversible_payload(conn):
    if "transfers" not in _tables(conn):
        return {"items": []}
    cols = _columns(conn, "transfers")
    rows = conn.execute(
        """
        SELECT * FROM transfers
        WHERE UPPER(COALESCE(status,''))='APLICADA'
          AND UPPER(COALESCE(operation_type,'')) NOT IN ('OPCIÓN DE COMPRA','DEVOLUCIÓN PRÉSTAMO')
        ORDER BY id DESC
        LIMIT 100
        """
    ).fetchall()
    items = []
    seen = set()
    for row in rows:
        keys = set(row.keys())
        group = row["deal_group"] if "deal_group" in keys and row["deal_group"] else None
        key = f"G:{group}" if group else f"O:{row['id']}"
        if key in seen:
            continue
        seen.add(key)
        deal = _deal_rows(conn, int(row["id"]))
        items.append(
            {
                "id": int(row["id"]),
                "operation_type": str(row["operation_type"] or "TRANSFERENCIA") if "operation_type" in cols else "TRANSFERENCIA",
                "seller": str(row["seller"] or ""),
                "buyer": str(row["buyer"] or ""),
                "amount": str(row["amount"] or "$0"),
                "players": [str(item["player"] or "") for item in deal],
            }
        )
        if len(items) >= 25:
            break
    return {"items": items}


def _runtime_modules():
    import clausulazo_patch as clauses
    import staff_admin_organized_patch as admin_tools
    import staff_review_channel_patch as staff_review

    if staff_review.APP is None or admin_tools.APP is None or clauses.APP is None:
        raise mobile_write_api.ApiFailure(
            "AJPA todavía está terminando de iniciar. Intentá nuevamente en unos segundos.",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
    return staff_review, clauses, admin_tools


def _perform_staff_action(kind: str, item_id: int, action: str, staff_id: int):
    staff_review, clauses, admin_tools = _runtime_modules()
    with guild_isolation_patch.guild_context(_mobile_guild_id()):
        if kind == "operations":
            if action == "approve":
                ok, error = staff_review._approve_deal(item_id, staff_id)
            elif action == "reject":
                ok, error = staff_review._reject_deal(item_id, staff_id)
            elif action == "pes":
                ok, error = staff_review._apply_deal_to_pes(item_id, staff_id)
            else:
                raise mobile_write_api.ApiFailure("Acción Staff inválida.")
            if not ok:
                raise mobile_write_api.ApiFailure(error or "No se pudo completar la operación.")
            return {"ok": True, "id": item_id, "action": action}

        if kind == "clauses":
            req = clauses.request_by_id(item_id)
            if not req:
                raise mobile_write_api.ApiFailure("Clausulazo no encontrado.", HTTPStatus.NOT_FOUND)
            if action == "approve":
                ok, result = clauses.approve_request(req, staff_id)
                if not ok:
                    raise mobile_write_api.ApiFailure(str(result or "No se pudo aprobar el clausulazo."))
                return {"ok": True, "id": item_id, "action": action, "transfer_id": int(result)}
            if action == "reject":
                ok = clauses.reject_request(req, staff_id)
                if not ok:
                    raise mobile_write_api.ApiFailure("El clausulazo ya fue resuelto.")
                return {"ok": True, "id": item_id, "action": action}
            raise mobile_write_api.ApiFailure("Acción de clausulazo inválida.")

        if kind == "reversible" and action == "undo":
            ok, result = admin_tools._undo_transfer(item_id, staff_id)
            if not ok:
                raise mobile_write_api.ApiFailure(str(result or "No se pudo deshacer el pase."))
            return {"ok": True, "id": item_id, "action": action, "reverted": len(result)}

    raise mobile_write_api.ApiFailure("Acción Staff inválida.")


def apply_mobile_staff_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_staff_api_patch", False):
        return

    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path not in {
            "/api/v1/admin/operations",
            "/api/v1/admin/clauses",
            "/api/v1/admin/reversible",
        }:
            return original_get(self)
        try:
            with mobile_write_api.write_db() as conn:
                mobile_write_api.ensure_schema(conn)
                _staff_session(self.headers, conn)
                if path.endswith("/operations"):
                    payload = operations_payload(conn)
                elif path.endswith("/clauses"):
                    payload = clauses_payload(conn)
                else:
                    payload = reversible_payload(conn)
                self._json(payload)
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            print(f"AJPA mobile Staff GET error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudo cargar la sección Staff."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        match = re.fullmatch(
            r"/api/v1/admin/(operations|clauses|reversible)/(\d+)/(approve|reject|pes|undo)",
            path,
        )
        if not match:
            return original_post(self)
        try:
            with mobile_write_api.write_db() as conn:
                mobile_write_api.ensure_schema(conn)
                session = _staff_session(self.headers, conn)
            kind, raw_id, action = match.groups()
            result = _perform_staff_action(kind, int(raw_id), action, int(session["user_id"]))
            self._json(result)
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            print(f"AJPA mobile Staff POST error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudo completar la operación Staff."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_staff_api_patch = True
    print("AJPA Mobile: Staff operations + clauses + undo endpoints enabled")
