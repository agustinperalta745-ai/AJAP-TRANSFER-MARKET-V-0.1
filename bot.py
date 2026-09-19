"""Railway compatibility entry point.

Railway is currently configured to start `python bot.py`. Keep that command
working, but route startup through run_bot.py so the AJAP patches are applied
before Discord connects.
"""

import os
import time

# Official AJPA Mobile download used by the periodic Radio Pasillo ad. Railway
# may override it later with AJPA_APP_DOWNLOAD_URL without requiring a code edit.
os.environ.setdefault(
    "AJPA_APP_DOWNLOAD_URL",
    "https://www.mediafire.com/file/m13t4jblgeb473c/AJPA-Transfer-Market-Actualizador.apk/file",
)

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
    # Champion announcements attach to the official close actions after the
    # canonical competition and Radio Pasillo layers are available.
    from radio_pasillo_final_events_patch import apply_radio_pasillo_final_events_patch
    apply_radio_pasillo_final_events_patch(runtime, bot)


guild_isolation_patch.apply_guild_isolation_patch = _apply_guild_isolation_and_league

import manager_menu_patch  # noqa: F401,E402
import league_channel_panel_patch  # noqa: F401,E402
# Legacy screenshot/OCR result ingestion is intentionally not loaded anymore.
# Official results are maintained in GES and synchronized by Staff.
import league_validation_admin_review_patch  # noqa: F401,E402
# Historical Zaragoza/Bolton corrections are score/date bounded. Future team
# identity is resolved through linked PES usernames, not a permanent Middlesbrough rewrite.
import league_zaragoza_bolton_history_fix_patch  # noqa: F401,E402
import league_market_channel_exemption_patch  # noqa: F401,E402
import guild_report_channel_bridge_patch  # noqa: F401,E402
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
import discord_departure_unassignment_patch  # noqa: F401,E402
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
# Every new player publication, whether created in Discord or AJPA Mobile, queues
# one deduplicated rumor for the canonical Radio Pasillo channel.
import radio_player_publication_patch  # noqa: F401,E402
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

# Keep the complete active AJPA team catalog available to standings/GES helpers.
import league_team_catalog_patch  # noqa: F401,E402

# One-time authoritative 03/09 audit: rebuild the current Pretemporada to the 38
# verified matches, named scorers + 3 own goals, refresh Discord standings, and
# wipe/repopulate the configured GES result channel cleanly.
import league_authoritative_audit_reconcile_patch  # noqa: F401,E402
# One-time, tightly bounded correction for the Ajax 2-2 PSG capture reported on
# 2026-09-03: Babel x2 / Pauleta x2. Never changes the official score.
import league_known_ajax_psg_scorer_fix_patch  # noqa: F401,E402
# Existing "Agregar goleador" cards must acknowledge Discord before DB/table work
# so old persistent buttons do not expire with "application did not respond".
import league_manual_scorer_button_timeout_fix_patch  # noqa: F401,E402
# Manual scorer editing is a Liga workflow, not a transfer-market interaction.
# Apply the exemption after the active market gate and scorer button wrappers.
import league_manual_scorer_market_gate_fix_patch  # noqa: F401,E402

# Final Radio Pasillo layer: compare the official Top 5 before/after each NEW
# league result. Only real overtakes within positions 1-5 create a post, with
# team emojis and a locally-rendered Top 5 image.
import league_top5_overtake_radio_patch  # noqa: F401,E402
# Visual identity repair: resolve canonical Liga names to the server's real club
# emojis and trim transparent PNG margins before rendering the Top 5 card.
import league_top5_badge_fix_patch  # noqa: F401,E402
# Persistence bridge: the same Top 5 event must also fire when a result becomes
# official later through evidence buttons, rival confirmation or Staff review.
import league_top5_persistence_bridge_patch  # noqa: F401,E402
# One-time end-to-end test: on the next ready event publish the current Top 5
# snapshot to Radio Pasillo without modifying any league data.
import league_top5_snapshot_test_patch  # noqa: F401,E402

# Permanent Staff controls stay available for corrections/history, but no image
# reader is allowed to create official results anymore.
import league_persistent_result_admin_controls_patch  # noqa: F401,E402
# Replace separate score/scorer forms with one simple persistent wizard:
# marcador -> equipo -> jugador de plantilla -> goles -> siguiente goleador.
import league_unified_match_manager_patch  # noqa: F401,E402
# Keep public #RESULTADO replies synchronized with the official corrected row,
# including a retroactive pass over recent already-corrected matches.
import league_result_message_sync_patch  # noqa: F401,E402

# Goleadores en Radio Pasillo: manda ahora una foto real del Top 5 y, después,
# vuelve a publicar solo cuando un goleador ya ubicado 1.º-5.º supera a otro.
import league_top5_scorers_radio_patch  # noqa: F401,E402
# Temporada 1: al quedar tres fechas o menos, Radio Pasillo activa automáticamente
# La Recta Final y publica una sola previa por fecha usando el estado oficial de GES.
import radio_pasillo_final_stretch_patch  # noqa: F401,E402

# Periodic Radio Pasillo reminders: every 90 minutes, rotate a short DT-facing
# feature tip. The AJPA Mobile download ad joins the rotation once its real URL
# is configured in AJPA_APP_DOWNLOAD_URL.
import radio_pasillo_feature_ads_patch  # noqa: F401,E402
# Requested one-shot: publish the clásico rival reminder immediately on the next
# successful start, once per guild, then resume the normal 90-minute cadence.
import radio_pasillo_classic_now_patch  # noqa: F401,E402

# Final safety layer: after every existing league/admin wrapper initializes, force
# Discord result-message ingestion off. GES is the single official source.
import league_disable_capture_ingest_patch  # noqa: F401,E402

# Every successful Staff "GES actualizada" sync publishes the complete official
# standings in Radio Pasillo with a short dynamic read of what changed.
import radio_pasillo_ges_table_patch  # noqa: F401,E402

# Final hard cap for the whole Radio Pasillo channel: every source shares one\n# 90-minute send slot, including GES, clásicos, market publications and reminders.\nimport radio_pasillo_rate_limit_patch  # noqa: F401,E402\n\n# Operational restart marker: keep this at the entry point so a source-only\n# redeploy restarts the Discord gateway without altering any persisted AJAP data.
AJAP_RESTART_MARKER = "2026-09-19T-radio-global-90m-v2"

import run_bot  # noqa: F401,E402
