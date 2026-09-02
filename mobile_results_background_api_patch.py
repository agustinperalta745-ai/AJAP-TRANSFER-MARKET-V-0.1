"""Serve the Results gallery background from AJPA's own mobile API origin.

React Native/Expo OTA clients already trust and reach the Railway API. Serving the
selected Pique 5-1 image from the same origin avoids Android image resolution
issues with OTA assets and raw GitHub URLs.
"""

from __future__ import annotations

import base64
import re
from functools import lru_cache
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

import mobile_read_api

_ROUTE = "/api/v1/assets/results-background.jpg"
_ROOT = Path(__file__).resolve().parent
_PARTS = tuple(_ROOT / "mobile" / "src" / f"bg_resultados_part{index}.ts" for index in range(4))


@lru_cache(maxsize=1)
def _results_background_bytes() -> bytes:
    chunks: list[str] = []
    for index, path in enumerate(_PARTS):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"=\s*'([A-Za-z0-9+/=]+)'\s*;", text)
        if not match:
            raise ValueError(f"Results background: invalid part {index}")
        chunks.append(match.group(1))

    body = base64.b64decode("".join(chunks), validate=True)
    if len(body) < 1024 or body[:3] != b"\xff\xd8\xff":
        raise ValueError("Results background: reconstructed file is not a valid JPEG")
    return body


def apply_mobile_results_background_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_results_background_api_patch", False):
        return

    original_get = handler.do_GET

    def patched_get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != _ROUTE:
            return original_get(self)

        try:
            body = _results_background_bytes()
            self.send_response(int(HTTPStatus.OK))
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            print(f"AJPA Results background API error: {type(exc).__name__}: {exc}")
            self._json(
                {
                    "error": "results_background_unavailable",
                    "message": "No se pudo cargar el fondo de Resultados.",
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    handler.do_GET = patched_get
    handler._ajpa_results_background_api_patch = True
    print("AJPA Mobile: Results background served from same-origin API")
