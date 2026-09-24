"""Global visual-theme API for AJPA Mobile.

All clients can read the active theme. Only paired Staff sessions can change it.
The configuration lives in the same guild SQLite database as the mobile API, so
visual changes apply to every device without requiring a new APK.
"""

from __future__ import annotations

import json
import re
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_read_api
import mobile_write_api

DEFAULT_THEME = {
    "accent": "#2d92ff",
    "accent_soft": "#8ac5ff",
    "background": "#02060a",
    "panel": "#08121c",
    "panel_alt": "#0b1824",
    "border": "#1f3447",
    "text": "#f7fbff",
    "muted": "#92a0ad",
    "success": "#45d47b",
    "danger": "#ff7880",
    "warning": "#ffc36f",
    "topbar": "#03080d",
    "card_radius": 18,
    "button_radius": 12,
    "content_padding": 16,
    "panel_opacity": 0.80,
    "image_opacity": 0.88,
    "shade_opacity": 0.24,
    "compact": False,
}

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_COLOR_KEYS = {
    "accent", "accent_soft", "background", "panel", "panel_alt", "border",
    "text", "muted", "success", "danger", "warning", "topbar",
}
_INT_LIMITS = {
    "card_radius": (4, 32),
    "button_radius": (4, 28),
    "content_padding": (8, 28),
}
_FLOAT_LIMITS = {
    "panel_opacity": (0.35, 1.0),
    "image_opacity": (0.10, 1.0),
    "shade_opacity": (0.0, 0.80),
}


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mobile_visual_theme (
            id INTEGER PRIMARY KEY CHECK(id=1),
            payload TEXT NOT NULL,
            updated_by INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _normalized_theme(payload) -> dict:
    source = payload.get("theme") if isinstance(payload, dict) and isinstance(payload.get("theme"), dict) else payload
    if not isinstance(source, dict):
        raise mobile_write_api.ApiFailure("Configuración visual inválida.")

    theme = dict(DEFAULT_THEME)
    for key in _COLOR_KEYS:
        if key not in source:
            continue
        value = str(source.get(key) or "").strip()
        if not _HEX.fullmatch(value):
            raise mobile_write_api.ApiFailure(f"Color inválido en {key}. Usá formato #RRGGBB.")
        theme[key] = value.lower()

    for key, (minimum, maximum) in _INT_LIMITS.items():
        if key not in source:
            continue
        try:
            value = int(source[key])
        except (TypeError, ValueError) as exc:
            raise mobile_write_api.ApiFailure(f"Valor inválido en {key}.") from exc
        theme[key] = max(minimum, min(maximum, value))

    for key, (minimum, maximum) in _FLOAT_LIMITS.items():
        if key not in source:
            continue
        try:
            value = float(source[key])
        except (TypeError, ValueError) as exc:
            raise mobile_write_api.ApiFailure(f"Valor inválido en {key}.") from exc
        theme[key] = round(max(minimum, min(maximum, value)), 3)

    if "compact" in source:
        theme["compact"] = bool(source["compact"])

    return theme


def _read_theme(conn) -> dict:
    _ensure_schema(conn)
    row = conn.execute(
        "SELECT payload, updated_at FROM mobile_visual_theme WHERE id=1"
    ).fetchone()
    if not row:
        return {"theme": dict(DEFAULT_THEME), "updated_at": None}
    try:
        stored = json.loads(str(row["payload"] or "{}"))
    except Exception:
        stored = {}
    merged = dict(DEFAULT_THEME)
    if isinstance(stored, dict):
        for key, value in stored.items():
            if key in merged:
                merged[key] = value
    return {"theme": merged, "updated_at": row["updated_at"]}


def _staff_session(headers, conn):
    session = mobile_write_api._session(headers, conn)
    if not session.get("is_staff"):
        raise mobile_write_api.ApiFailure(
            "El editor visual es exclusivo para Staff.",
            HTTPStatus.FORBIDDEN,
        )
    return session


def apply_mobile_theme_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_theme_api_patch", False):
        return

    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/theme":
            return original_get(self)
        try:
            with mobile_write_api.write_db() as conn:
                self._json(_read_theme(conn))
        except Exception as exc:
            print(f"AJPA visual theme read error: {type(exc).__name__}: {exc}")
            self._json(
                {"theme": dict(DEFAULT_THEME), "updated_at": None},
                HTTPStatus.OK,
            )

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path not in {"/api/v1/admin/theme", "/api/v1/admin/theme/reset"}:
            return original_post(self)
        try:
            with mobile_write_api.write_db() as conn:
                session = _staff_session(self.headers, conn)
                _ensure_schema(conn)
                if path.endswith("/reset"):
                    conn.execute("DELETE FROM mobile_visual_theme WHERE id=1")
                    conn.commit()
                    self._json({"ok": True, **_read_theme(conn)})
                    return

                payload = mobile_write_api._read_json(self)
                theme = _normalized_theme(payload)
                conn.execute(
                    """
                    INSERT INTO mobile_visual_theme(id,payload,updated_by,updated_at)
                    VALUES(1,?,?,CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        payload=excluded.payload,
                        updated_by=excluded.updated_by,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (json.dumps(theme, ensure_ascii=False, separators=(",", ":")), int(session["user_id"])),
                )
                conn.commit()
                self._json({"ok": True, **_read_theme(conn)})
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            print(f"AJPA visual theme write error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudo guardar la estética."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_theme_api_patch = True
    print("AJPA Mobile: global visual theme API enabled")
