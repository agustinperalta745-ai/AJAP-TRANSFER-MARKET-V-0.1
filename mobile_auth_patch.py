"""Attach Discord-authenticated /api/v1/me to the read-only mobile server."""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlparse

import mobile_auth
import mobile_read_api


def apply_mobile_auth_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_auth_patch", False):
        return

    original_get = handler.do_GET

    def authenticated_get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/me":
            return original_get(self)
        try:
            with mobile_read_api.readonly_db() as conn:
                payload = mobile_auth.me_payload(
                    conn,
                    self.headers.get("Authorization"),
                )
            self._json(payload)
        except mobile_auth.OAuthError as exc:
            self._json(
                {"error": "oauth", "message": exc.message},
                exc.status,
            )
        except FileNotFoundError as exc:
            self._json(
                {"error": "database_not_found", "message": str(exc)},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            print(f"AJPA mobile auth error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    handler.do_GET = authenticated_get
    handler._ajpa_mobile_auth_patch = True
