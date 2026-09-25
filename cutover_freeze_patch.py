"""Final read-only guard used during Railway -> Northflank cutover."""

from __future__ import annotations

import os
from http import HTTPStatus

import mobile_read_api


def apply_cutover_freeze_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_cutover_freeze_patch", False):
        return

    original_get = handler.do_GET
    original_post = handler.do_POST

    def frozen() -> bool:
        return (os.getenv("AJPA_CUTOVER_FREEZE") or "").strip().lower() in {"1","true","yes","on"}

    def guarded_get(self):
        if frozen() and self.headers.get("X-AJPA-Method"):
            self._json(
                {"error":"maintenance","message":"AJPA está migrando de servidor. Probá nuevamente en unos minutos."},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        return original_get(self)

    def guarded_post(self):
        if frozen():
            self._json(
                {"error":"maintenance","message":"AJPA está migrando de servidor. Probá nuevamente en unos minutos."},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        return original_post(self)

    handler.do_GET = guarded_get
    handler.do_POST = guarded_post
    handler._ajpa_cutover_freeze_patch = True
    print("AJPA cutover freeze guard armed")
