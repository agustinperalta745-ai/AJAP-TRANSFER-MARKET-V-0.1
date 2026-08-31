"""Transport hardening for AJPA Mobile.

Android can read AJPA reliably over GET while some Railway/mobile paths reset
requests that use mutation verbs. Pairing already proved the GET path is stable,
so authenticated mutations can use an explicit GET tunnel while preserving the
original API route, payload and authorization checks on the server.
"""

from __future__ import annotations

import io
import json
from http import HTTPStatus
from urllib.parse import unquote, urlparse

import mobile_read_api
import mobile_write_api


def apply_mobile_transport_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_transport_patch", False):
        return

    # Apply this patch LAST, after every write-route patch. The captured POST
    # handler therefore contains publications, Staff, Clausulazo, match search,
    # resignation and any other mutation exposed to the app.
    original_get = handler.do_GET
    original_post = handler.do_POST

    def robust_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-AJPA-Pair-Code, X-AJPA-Method, X-AJPA-Body",
        )
        self.end_headers()
        if int(status) != int(HTTPStatus.NO_CONTENT):
            self.wfile.write(body)

    def robust_options(self):
        self._json({}, HTTPStatus.NO_CONTENT)

    def _run_tunneled_mutation(self):
        requested = str(self.headers.get("X-AJPA-Method") or "").strip().upper()
        if requested not in {"POST", "PUT", "PATCH", "DELETE"}:
            raise mobile_write_api.ApiFailure(
                "Método de operación móvil inválido.", HTTPStatus.BAD_REQUEST
            )

        encoded = str(self.headers.get("X-AJPA-Body") or "")
        try:
            body = unquote(encoded).encode("utf-8") if encoded else b"{}"
        except Exception as exc:
            raise mobile_write_api.ApiFailure(
                "No se pudo leer la operación móvil.", HTTPStatus.BAD_REQUEST
            ) from exc
        if len(body) > 64_000:
            raise mobile_write_api.ApiFailure(
                "Solicitud demasiado grande.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            )

        previous_rfile = self.rfile
        previous_command = getattr(self, "command", "GET")
        had_length = "Content-Length" in self.headers
        previous_length = self.headers.get("Content-Length")
        try:
            self.rfile = io.BytesIO(body)
            self.command = requested
            if had_length:
                self.headers.replace_header("Content-Length", str(len(body)))
            else:
                self.headers.add_header("Content-Length", str(len(body)))
            return original_post(self)
        finally:
            self.rfile = previous_rfile
            self.command = previous_command
            if had_length:
                self.headers.replace_header("Content-Length", previous_length or "0")
            elif "Content-Length" in self.headers:
                del self.headers["Content-Length"]

    def robust_get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"

        # Common reliable transport for every authenticated mutation. The app
        # keeps the bearer token in Authorization; only the HTTP transport verb
        # changes. All business rules still execute in the original POST stack.
        if self.headers.get("X-AJPA-Method"):
            try:
                return _run_tunneled_mutation(self)
            except mobile_write_api.ApiFailure as exc:
                self._json({"error": "request", "message": exc.message}, exc.status)
                return
            except Exception as exc:
                print(f"AJPA mobile mutation tunnel error: {type(exc).__name__}: {exc}")
                self._json(
                    {
                        "error": "internal_error",
                        "message": "No se pudo completar la operación móvil.",
                    },
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
                return

        if path != "/api/v1/auth/pair":
            return original_get(self)

        code = str(self.headers.get("X-AJPA-Pair-Code") or "").strip()
        try:
            if not code:
                raise mobile_write_api.ApiFailure(
                    "Falta el código de vinculación.",
                    HTTPStatus.BAD_REQUEST,
                )
            self._json(mobile_write_api.exchange_pair_code(code), HTTPStatus.OK)
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            print(f"AJPA mobile pair fallback error: {type(exc).__name__}: {exc}")
            self._json(
                {
                    "error": "internal_error",
                    "message": "No se pudo vincular la cuenta en este momento.",
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    handler._json = robust_json
    handler.do_OPTIONS = robust_options
    handler.do_GET = robust_get
    handler._ajpa_mobile_transport_patch = True
    print("AJPA Mobile: reliable GET mutation tunnel + pairing fallback enabled")
