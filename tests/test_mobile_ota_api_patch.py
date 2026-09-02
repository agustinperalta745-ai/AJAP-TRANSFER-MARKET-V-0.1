import json
import unittest
from unittest.mock import patch

import mobile_ota_api_patch as ota


class _FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


class MobileOtaApiPatchTests(unittest.TestCase):
    def test_accepts_matching_runtime_manifest(self):
        payload = {
            "id": "11111111-1111-4111-8111-111111111111",
            "createdAt": "2026-09-02T00:00:00.000Z",
            "runtimeVersion": "1",
            "launchAsset": {
                "key": "bundle",
                "contentType": "application/javascript",
                "url": "https://example.invalid/bundle.js",
            },
            "assets": [],
            "metadata": {},
            "extra": {},
        }
        with patch(
            "mobile_ota_api_patch.urllib.request.urlopen",
            return_value=_FakeResponse(payload),
        ):
            result = ota._load_remote_manifest("1", "android")
        self.assertEqual(result, payload)

    def test_rejects_manifest_for_other_runtime(self):
        payload = {
            "id": "11111111-1111-4111-8111-111111111111",
            "runtimeVersion": "2",
            "launchAsset": {"url": "https://example.invalid/bundle.js"},
        }
        with patch(
            "mobile_ota_api_patch.urllib.request.urlopen",
            return_value=_FakeResponse(payload),
        ):
            result = ota._load_remote_manifest("1", "android")
        self.assertIsNone(result)

    def test_latest_url_uses_immutable_ota_branch(self):
        url = ota._latest_manifest_url("1", "android")
        self.assertIn("/ota-updates/mobile/ota/latest-1-android.json", url)


if __name__ == "__main__":
    unittest.main()
