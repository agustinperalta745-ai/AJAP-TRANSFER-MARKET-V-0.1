"""AJPA startup that serves Discord + the read-only mobile API."""

import os

# sitecustomize resolves the guild-aware persistent DB_PATH before the API starts.
import sitecustomize  # noqa: F401

os.environ.setdefault("AJPA_MOBILE_API_ENABLED", "1")
# Production mobile app must read the definitive AJPA Discord server by default.
# Railway can still override this explicitly with AJPA_MOBILE_GUILD_ID if needed.
os.environ.setdefault("AJPA_MOBILE_GUILD_ID", "1541577795426324571")

import mobile_auth_patch  # noqa: E402
from mobile_read_api import start_mobile_read_api  # noqa: E402

# Add authenticated /api/v1/me while keeping every market endpoint read-only.
mobile_auth_patch.apply_mobile_auth_patch()
start_mobile_read_api()

# Keep every existing bot guard/patch/startup exactly as production uses it.
import bot  # noqa: F401,E402
