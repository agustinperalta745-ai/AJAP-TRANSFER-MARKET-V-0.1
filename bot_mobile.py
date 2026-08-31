"""AJPA startup that serves Discord + the operational mobile API."""

import os

# sitecustomize resolves the guild-aware persistent DB_PATH before the API starts.
import sitecustomize  # noqa: F401

os.environ.setdefault("AJPA_MOBILE_API_ENABLED", "1")
# Production mobile app must read/write the definitive AJPA Discord server by default.
# Railway can still override this explicitly with AJPA_MOBILE_GUILD_ID if needed.
os.environ.setdefault("AJPA_MOBILE_GUILD_ID", "1541577795426324571")

import mobile_auth_patch  # noqa: E402
import mobile_write_api  # noqa: E402
import mobile_clausulazo_api_patch  # noqa: E402
import mobile_write_release_compat  # noqa: E402
import mobile_transport_patch  # noqa: E402
import mobile_parity_api_patch  # noqa: E402
import mobile_staff_api_patch  # noqa: E402
import mobile_staff_economy_api_patch  # noqa: E402
import mobile_match_search_patch  # noqa: E402
import mobile_resignation_api_patch  # noqa: E402
import league_team_catalog_patch  # noqa: E402
# Must be imported BEFORE bot.py/run_bot.py so /app_codigo is registered on the
# final per-guild runtime before Discord connects.
import mobile_pairing_bootstrap_patch  # noqa: F401,E402
from mobile_read_api import start_mobile_read_api  # noqa: E402

# Keep the result reader aligned with the current active clubs before Discord
# imports the league modules and builds their canonical team prompts.
league_team_catalog_patch.apply_league_team_catalog_patch()

# Keep OAuth-compatible /api/v1/me and add paired, authenticated write routes.
mobile_write_release_compat.apply()
mobile_auth_patch.apply_mobile_auth_patch()
mobile_write_api.apply_mobile_write_patch()
# Real mobile clausulazo requests; Staff approval/rejection remains shared with Discord.
mobile_clausulazo_api_patch.apply_mobile_clausulazo_api_patch()
# Adds real Liga/history reads plus narrowly scoped Staff mobile endpoints.
mobile_parity_api_patch.apply_mobile_parity_api_patch()
# Staff Mercado parity: pending operations, clausulazo review and safe undo.
mobile_staff_api_patch.apply_mobile_staff_api_patch()
# Staff Economia parity: audited Dar/Quitar dinero using the same Discord ledger.
mobile_staff_economy_api_patch.apply_mobile_staff_economy_api_patch()
# Public Buscar Partido board + authenticated create/join/cancel operations.
# Joining consults the official league_matches table populated by the result bot.
mobile_match_search_patch.apply_mobile_match_search_patch()
# Real club resignation: frees only the manager assignment and keeps roster/economy.
mobile_resignation_api_patch.apply_mobile_resignation_api_patch()
# IMPORTANT: transport is last so the reliable GET tunnel captures every mutation
# route installed above instead of bypassing later wrappers.
mobile_transport_patch.apply_mobile_transport_patch()
start_mobile_read_api()

# Keep every existing bot guard/patch/startup exactly as production uses it.
import bot  # noqa: F401,E402
