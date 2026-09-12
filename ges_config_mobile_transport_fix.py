"""Keep Android's GET mutation tunnel authoritative after late GES route installs.

AJPA Mobile sends mutations through GET with X-AJPA-Method because that transport
is the reliable path from the APK to Railway. The per-competition GES layer is
installed later during Discord startup and adds its own GET /admin/ges-config
handler. Without this final wrapper, a tunneled POST to that same URL is mistaken
for a normal GET: the backend returns the old config, the app thinks save
succeeded, then clears the three fields.

This wrapper is installed immediately after the GES authority routes, so tunneled
mutations always reach the final POST handler while ordinary GET requests keep the
existing route stack unchanged.
"""

from __future__ import annotations

import io
from http import HTTPStatus
from urllib.parse import unquote

import mobile_read_api
import mobile_write_api


def apply_final_ges_mobile_mutation_tunnel() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_final_ges_mobile_mutation_tunnel", False):
        return

    final_get = handler.do_GET

    def get(self):
        requested = str(self.headers.get("X-AJPA-Method") or "").strip().upper()
        if not requested:
            return final_get(self)

        try:
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
                # Resolve dynamically: the GES authority POST handler is already
                # installed and must receive /api/v1/admin/ges-config.
                return handler.do_POST(self)
            finally:
                self.rfile = previous_rfile
                self.command = previous_command
                if had_length:
                    self.headers.replace_header("Content-Length", previous_length or "0")
                elif "Content-Length" in self.headers:
                    del self.headers["Content-Length"]

        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            print(f"AJPA final GES mutation tunnel error: {type(exc).__name__}: {exc}")
            self._json(
                {
                    "error": "internal_error",
                    "message": "No se pudo guardar la configuración GES.",
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    handler.do_GET = get
    handler._ajpa_final_ges_mobile_mutation_tunnel = True
    print("AJPA Mobile: túnel final de guardado GES activo")
