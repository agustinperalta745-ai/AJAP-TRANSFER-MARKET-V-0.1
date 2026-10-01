"""Servidor web mínimo para la vista previa PWA de AJPA Transfer Market.

Se ejecuta como un servicio separado del bot de Discord:
    python pwa_preview.py

Railway inyecta PORT automáticamente.
"""

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent / "web"


class PWAHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def end_headers(self):
        if self.path.endswith("/sw.js") or self.path == "/sw.js":
            self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), PWAHandler)
    print(f"AJPA PWA preview listening on 0.0.0.0:{port}")
    server.serve_forever()
