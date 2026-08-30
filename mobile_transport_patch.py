"""Transport hardening for AJPA Mobile.

Keeps the existing API behavior, but makes Android pairing resilient when a
POST request is rejected/reset somewhere between the APK and Railway. The APK
can retry the one-time pair exchange over GET using a private request header.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_read_api
import mobile_write_api


def apply_mobile_transport_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_transport_patch", False):
        return

    original_get = handler.do_GET

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
            "Content-Type, Authorization, X-AJPA-Pair-Code",
        )
        self.end_headers()
        if int(status) != int(HTTPStatus.NO_CONTENT):
            self.wfile.write(body)

    def robust_options(self):
        self._json({}, HTTPStatus.NO_CONTENT)

    def robust_get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
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
    print("AJPA Mobile: transport hardening + pairing fallback enabled")
