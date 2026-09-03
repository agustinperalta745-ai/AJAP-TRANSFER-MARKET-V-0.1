"""Railway compatibility entry point.

Railway is currently configured to start `python bot.py`. Keep that command
working, but route startup through run_bot.py so the AJAP patches are applied
before Discord connects.
"""

import os
import time

PRIMARY_RAILWAY_PROJECT_ID = (
    os.getenv("AJAP_PRIMARY_RAILWAY_PROJECT_ID")
    or "6abcd5b2-6995-4e18-b7f1-be32f6298fdc"
).strip()
CURRENT_RAILWAY_PROJECT_ID = (os.getenv("RAILWAY_PROJECT_ID") or "").strip()

if (
    CURRENT_RAILWAY_PROJECT_ID
    and PRIMARY_RAILWAY_PROJECT_ID
    and CURRENT_RAILWAY_PROJECT_ID != PRIMARY_RAILWAY_PROJECT_ID
):
    print(
        "AJAP secondary Railway deployment detected: Discord gateway disabled | "
        f"current_project={CURRENT_RAILWAY_PROJECT_ID} | "
        f"primary_project={PRIMARY_RAILWAY_PROJECT_ID}"
    )
    while True:
        time.sleep(3600)

import newcastle_extension  # noqa: F401,E402
import everton_extension  # noqa: F401,E402
import additional_roster_sync_patch  # noqa: F401,E402
import betis_roster_replace_patch  # noqa: F401,E402
import sevilla_roster_replace_patch  # noqa: F401,E402
import villarreal_roster_replace_patch  # noqa: F401,E402
import torino_roster_patch  # noqa: F401,E402
import fiorentina_roster_patch  # noqa: F401,E402
import lazio_roster_patch  # noqa: F401,E402
import fulham_roster_patch  # noqa: F401,E402
import bolton_wanderers_roster_patch  # noqa: F401,E402
import middlesbrough_roster_patch  # noqa: F401,E402
import manchester_city_roster_patch  # noqa: F401,E402
import west_ham_united_roster_patch  # noqa: F401,E402

import member_nickname_patch  # noqa: F401,E402
import vacancy_nickname_patch  # noqa: F401,E402
import selector_nickname_patch  # noqa: F401,E402
import dt_resignation_patch  # noqa: F401,E402
import mobile_resignation_discord_bridge_patch  # noqa: F401,E402

# Liga + ciclo oficial comparten la misma DB aislada por servidor. El ciclo se
# instala DESPUÉS de Liga para etiquetar resultados sin borrar el historial global.
import guild_isolation_patch
from league_automation_patch import apply_league_automation_patch
from competition_cycle import apply_competition_cycle

_original_apply_guild_isolation_patch = guild_isolation_patch.apply_guild_isolation_patch


def _apply_guild_isolation_and_league(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_league_automation_patch(runtime, bot)
    apply_competition_cycle(runtime, bot)


guild_isolation_patch.apply_guild_isolation_patch = _apply_guild_isolation_and_league

import manager_menu_patch  # noqa: F401,E402
import league_channel_panel_patch  # noqa: F401,E402
import league_result_confirmation_patch  # noqa: F401,E402
import league_validation_admin_review_patch  # noqa: F401,E402
import league_result_evidence_patch  # noqa: F401,E402
# Historical Zaragoza/Bolton corrections are score/date bounded. Future team
# identity is resolved through linked PES usernames, not a permanent Middlesbrough rewrite.
import league_zaragoza_bolton_history_fix_patch  # noqa: F401,E402
import league_capture_rehab_patch  # noqa: F401,E402
import league_market_channel_exemption_patch  # noqa: F401,E402
import guild_report_channel_bridge_patch  # noqa: F401,E402
import league_api_error_diagnostic_patch  # noqa: F401,E402
import league_text_result_patch  # noqa: F401,E402
import league_result_feedback_patch  # noqa: F401,E402
import manager_selector_patch  # noqa: F401,E402
import my_club_menu_patch  # noqa: F401,E402
import staff_dashboard_patch  # noqa: F401,E402
import staff_admin_organized_patch  # noqa: F401,E402
import competition_cycle_admin_ui_patch  # noqa: F401,E402
import league_admin_config_location_patch  # noqa: F401,E402
# Must run after the format patch: it keeps ida/vuelta limits but scopes them to
# the active competition so old seasons never block new fixtures.
import competition_scope_guards_patch  # noqa: F401,E402
import staff_profile_gate_patch  # noqa: F401,E402
import admin_roster_builder_patch  # noqa: F401,E402
import admin_team_delete_patch  # noqa: F401,E402
import roster_catalog_autosync_patch  # noqa: F401,E402
import club_assignment_consistency_patch  # noqa: F401,E402
import assignment_history_authority_patch  # noqa: F401,E402
import admin_rosters_visual_patch  # noqa: F401,E402
import admin_roster_view_selector_patch  # noqa: F401,E402
import roster_player_stats_patch  # noqa: F401,E402
import market_player_stats_patch  # noqa: F401,E402
import loan_canon_patch  # noqa: F401,E402
import loan_canon_cap_patch  # noqa: F401,E402
import treasury_menu_patch  # noqa: F401,E402
import staff_treasury_patch  # noqa: F401,E402
import loan_purchase_staff_notification_patch  # noqa: F401,E402
import publication_submit_guild_schema_patch  # noqa: F401,E402
import loan_publication_cap_guard_patch  # noqa: F401,E402
import discord_modal_guild_context_compat_patch  # noqa: F401,E402
import resignation_consistency_patch  # noqa: F401,E402
import json_team_selection_patch  # noqa: F401,E402
import team_badge_selector_patch  # noqa: F401,E402
import badge_reliability_patch  # noqa: F401,E402
import modal_submit_hardening_patch  # noqa: F401,E402
import guided_search_select_fix_patch  # noqa: F401,E402
import player_release_patch  # noqa: F401,E402
import release_button_visual_patch  # noqa: F401,E402
import market_access_role_patch  # noqa: F401,E402

# Final identity layers: PES username wins over the in-game club label, and every
# active manager must have that link before entering the rest of /mercado.
import pes_username_link_patch  # noqa: F401,E402
import pes_market_entry_gate_patch  # noqa: F401,E402
# Final result-reader enrichment: recover clearly visible PES6 scorers without
# attributing blank-name goal rows to the player above them.
import league_scorer_continuation_rows_patch  # noqa: F401,E402
# OpenAI can transiently refuse a vision request (429/5xx/timeout). Retry both
# the main result read and the dedicated scorer-detail pass before giving up.
import league_openai_retry_patch  # noqa: F401,E402
# A clear score must stay automatic even if player names are uncertain. The
# result-only rescue validates teams/score separately and scorer OCR is optional.
import league_result_autonomy_patch  # noqa: F401,E402
# Free local OCR is the first reader: Railway/ONNX handles screenshots locally.
import league_local_ocr_patch  # noqa: F401,E402
# Normalize full-phone screenshots before OCR so the PES frame is large enough
# and username/team/score coordinates are measured against the game image.
import league_phone_screenshot_crop_patch  # noqa: F401,E402
# Official teams + numeric PES score are sufficient to accept a structurally
# valid result, while scorer OCR remains independent.
import league_result_acceptance_guard_patch  # noqa: F401,E402
# Combine photo geometry, team text, uploader club and linked PES username.
import league_multisignal_result_patch  # noqa: F401,E402
# Final runtime reliability: local/multisignal first, automatic OpenAI rescue on
# failure/weak reads, and concrete exception diagnostics instead of generic errors.
import league_runtime_result_rescue_patch  # noqa: F401,E402
# Re-run unresolved historical review cards once per restart through the newest
# reader so already-posted captures/results/goleadores are recovered automatically.
import league_pending_review_reprocess_patch  # noqa: F401,E402
# Safety bridge: pending recovery gets runtime rescue, and the Staff rehab test
# can never delete an already official result/goleador record.
import league_result_final_safety_patch  # noqa: F401,E402
# One-time, tightly bounded correction for the Ajax 2-2 PSG capture reported on
# 2026-09-03: Babel x2 / Pauleta x2. Never changes the official score.
import league_known_ajax_psg_scorer_fix_patch  # noqa: F401,E402
# Existing "Agregar goleador" cards must acknowledge Discord before DB/table work
# so old persistent buttons do not expire with "application did not respond".
import league_manual_scorer_button_timeout_fix_patch  # noqa: F401,E402

# Operational restart marker: keep this at the entry point so a source-only
# redeploy restarts the Discord gateway without altering any persisted AJAP data.
AJAP_RESTART_MARKER = "2026-09-03T-result-final-safety"

import run_bot  # noqa: F401,E402