"""Self-hosted Expo Updates manifest proxy for the AJPA Android app.

The Android binary points expo-updates at this Railway endpoint. OTA bundles are
published to the repository's ``ota-updates`` branch by a dedicated workflow.
Railway only proxies the latest protocol-v1 manifest; immutable bundle/assets are
served directly from raw.githubusercontent.com.

Keeping OTA payloads on a separate branch means publishing a JS-only update does
not rebuild the APK or mutate the production SQLite database.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_read_api

OTA_RUNTIME_VERSION = "1"
OTA_REPOSITORY = "agustinperalta745-ai/AJAP-TRANSFER-MARKET-V-0.1"
OTA_BRANCH = "ota-updates"
OTA_RAW_ROOT = (
    f"https://raw.githubusercontent.com/{OTA_REPOSITORY}/{OTA_BRANCH}/mobile/ota"
)


def _latest_manifest_url(runtime_version: str, platform: str) -> str:
    # A cache-busting query keeps the Railway proxy from observing an older
    # GitHub raw pointer immediately after Staff publishes a new OTA release.
    stamp = int(time.time() // 30)
    return (
        f"{OTA_RAW_ROOT}/latest-{runtime_version}-{platform}.json"
        f"?ajpa_ota={stamp}"
    )


def _load_remote_manifest(runtime_version: str, platform: str) -> dict | None:
    url = _latest_manifest_url(runtime_version, platform)
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "AJPA-Mobile-OTA/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status != HTTPStatus.OK:
                return None
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == HTTPStatus.NOT_FOUND:
            return None
        raise
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    if str(payload.get("runtimeVersion") or "") != runtime_version:
        return None
    if not payload.get("id") or not payload.get("launchAsset"):
        return None
    return payload


def _send_no_update(handler) -> None:
    handler.send_response(HTTPStatus.NO_CONTENT)
    handler.send_header("expo-protocol-version", "1")
    handler.send_header("expo-sfv-version", "0")
    handler.send_header("Cache-Control", "private, max-age=0, no-store")
    handler.end_headers()


def _send_manifest(handler, manifest: dict) -> None:
    body = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "application/expo+json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("expo-protocol-version", "1")
    handler.send_header("expo-sfv-version", "0")
    handler.send_header("Cache-Control", "private, max-age=0, no-store")
    handler.end_headers()
    handler.wfile.write(body)


def apply_mobile_ota_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_ota_api_patch", False):
        return

    original_get = handler.do_GET

    def ota_get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path == "/api/v1/ota/status":
            runtime_version = OTA_RUNTIME_VERSION
            manifest = _load_remote_manifest(runtime_version, "android")
            self._json(
                {
                    "enabled": True,
                    "runtime_version": runtime_version,
                    "published": bool(manifest),
                    "update_id": manifest.get("id") if manifest else None,
                }
            )
            return

        if path != "/api/v1/ota/manifest":
            return original_get(self)

        protocol = str(self.headers.get("expo-protocol-version") or "1").strip()
        platform = str(self.headers.get("expo-platform") or "").strip().lower()
        runtime_version = str(
            self.headers.get("expo-runtime-version") or ""
        ).strip()

        if protocol not in {"0", "1"}:
            self._json(
                {"error": "unsupported_protocol"},
                HTTPStatus.BAD_REQUEST,
            )
            return
        if platform != "android" or not runtime_version:
            self._json(
                {"error": "invalid_update_request"},
                HTTPStatus.BAD_REQUEST,
            )
            return
        if runtime_version != OTA_RUNTIME_VERSION:
            _send_no_update(self)
            return

        manifest = _load_remote_manifest(runtime_version, platform)
        if not manifest:
            _send_no_update(self)
            return

        current_update_id = str(
            self.headers.get("expo-current-update-id") or ""
        ).strip().lower()
        latest_update_id = str(manifest.get("id") or "").strip().lower()
        if current_update_id and current_update_id == latest_update_id:
            _send_no_update(self)
            return

        _send_manifest(self, manifest)

    handler.do_GET = ota_get
    handler._ajpa_mobile_ota_api_patch = True
    print(
        "AJPA Mobile OTA: Expo Updates protocol v1 proxy enabled "
        f"• runtime={OTA_RUNTIME_VERSION}"
    )
