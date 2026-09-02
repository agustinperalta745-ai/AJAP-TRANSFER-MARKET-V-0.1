"""AJPA startup that serves Discord + the operational mobile API."""

import os

import sitecustomize  # noqa: F401

os.environ.setdefault("AJPA_MOBILE_API_ENABLED", "1")
os.environ.setdefault("AJPA_MOBILE_GUILD_ID", "1541577795426324571")

import mobile_auth_patch  # noqa: E402
import mobile_write_api  # noqa: E402
import mobile_clausulazo_api_patch  # noqa: E402
import mobile_write_release_compat  # noqa: E402
import mobile_transport_patch  # noqa: E402
import mobile_parity_api_patch  # noqa: E402
import mobile_league_history_api_patch  # noqa: E402
import mobile_competition_cycle_api_patch  # noqa: E402
import mobile_staff_api_patch  # noqa: E402
import mobile_staff_economy_api_patch  # noqa: E402
import mobile_club_profiles_api_patch  # noqa: E402
import mobile_club_profiles_runtime_fix  # noqa: E402
import mobile_classic_rival_api_patch  # noqa: E402
import mobile_match_search_patch  # noqa: E402
import mobile_match_result_timeout_patch  # noqa: E402
import mobile_resignation_api_patch  # noqa: E402
import mobile_ota_api_patch  # noqa: E402
import mobile_results_background_api_patch  # noqa: E402
import league_team_catalog_patch  # noqa: E402
import mobile_pairing_bootstrap_patch  # noqa: F401,E402
from mobile_read_api import start_mobile_read_api  # noqa: E402

league_team_catalog_patch.apply_league_team_catalog_patch()

mobile_write_release_compat.apply()
mobile_auth_patch.apply_mobile_auth_patch()
mobile_write_api.apply_mobile_write_patch()
mobile_clausulazo_api_patch.apply_mobile_clausulazo_api_patch()
mobile_parity_api_patch.apply_mobile_parity_api_patch()
mobile_league_history_api_patch.apply_mobile_league_history_api_patch()
# Must run after league history: it keeps historical cards untouched and replaces
# only current standings/scorers with the active competition slice.
mobile_competition_cycle_api_patch.apply_mobile_competition_cycle_api_patch()
mobile_staff_api_patch.apply_mobile_staff_api_patch()
mobile_staff_economy_api_patch.apply_mobile_staff_economy_api_patch()
mobile_club_profiles_api_patch.apply_mobile_club_profiles_api_patch()
mobile_club_profiles_runtime_fix.apply_mobile_club_profiles_runtime_fix()
mobile_classic_rival_api_patch.apply_mobile_classic_rival_api_patch()
mobile_match_search_patch.apply_mobile_match_search_patch()
mobile_match_result_timeout_patch.apply_mobile_match_result_timeout_patch()
mobile_resignation_api_patch.apply_mobile_resignation_api_patch()
mobile_ota_api_patch.apply_mobile_ota_api_patch()
mobile_results_background_api_patch.apply_mobile_results_background_api_patch()
# Transport stays last so its GET tunnel captures every authenticated mutation.
mobile_transport_patch.apply_mobile_transport_patch()
start_mobile_read_api()

import bot  # noqa: F401,E402