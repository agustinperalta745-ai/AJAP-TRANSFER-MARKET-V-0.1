"""Keep the selectable team catalog in sync with loaded rosters.

AJPA rule: every team that is actually loaded must be selectable. We rebuild the
catalog on demand from two safe sources:
- current roster_players clubs (JSON/seed/admin-loaded teams), and
- the built-in OFFICIAL_TEAMS fallback, so an older guild database with an empty
  league_teams table cannot render "no active teams" after a deploy.

Important: this patch must be INSTALLED after admin_team_delete_patch has applied.
That module replaces builder._active_teams at runtime. The previous version patched
builder._active_teams too early (module import time), so the delete patch silently
overwrote the autosync and the user selector still saw an empty catalog.

Staff-deleted teams remain hidden unless a roster for that club exists again. A
new roster is treated as an intentional reload and clears the old tombstone.
"""

from __future__ import annotations

import admin_roster_builder_patch as builder
import guild_isolation_patch as guild_isolation
import team_assignment as teams


_ORIGINAL_ACTIVE_TEAMS = None
_ORIGINAL_OFFICIAL_NAME = None


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _country_for(club: str) -> str:
    wanted = str(club or "").strip().casefold()
    for name, country in getattr(teams, "OFFICIAL_TEAMS", []):
        if str(name).strip().casefold() == wanted:
            return str(country or "Sin definir")
    if wanted == "real betis":
        return "España"
    return "Sin definir"


def _is_deleted(conn, club: str) -> bool:
    if not _table_exists(conn, "deleted_teams"):
        return False
    return bool(
        conn.execute(
            "SELECT 1 FROM deleted_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
            (club,),
        ).fetchone()
    )


def _upsert_catalog(conn, club: str, country: str):
    existing = conn.execute(
        "SELECT country FROM league_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
        (club,),
    ).fetchone()
    final_country = (
        str(existing["country"] or "").strip()
        if existing and str(existing["country"] or "").strip()
        else str(country or "Sin definir").strip() or "Sin definir"
    )

    conn.execute(
        """
        INSERT INTO league_teams (name, country, active)
        VALUES (?, ?, 1)
        ON CONFLICT(name) DO UPDATE SET
            country = CASE
                WHEN TRIM(COALESCE(league_teams.country, '')) = '' THEN excluded.country
                ELSE league_teams.country
            END,
            active = 1
        """,
        (club, final_country),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO club_finances (club, balance, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        """,
        (club, builder.INITIAL_TEAM_BUDGET),
    )


def _sync_loaded_teams_into_catalog():
    app = builder.APP
    if app is None:
        return

    builder._ensure_schema()
    with app.db() as conn:
        # 1) Repair old/stale guild DBs from the current built-in catalog. Do not
        # resurrect a club Staff explicitly deleted.
        for raw_name, raw_country in getattr(teams, "OFFICIAL_TEAMS", []):
            club = str(raw_name or "").strip()
            if not club or _is_deleted(conn, club):
                continue
            _upsert_catalog(conn, club, str(raw_country or "Sin definir"))

        # 2) Any club with a real roster is loaded, including future JSON teams.
        # A roster reappearing after deletion means Staff deliberately reloaded it.
        clubs = conn.execute(
            """
            SELECT DISTINCT TRIM(club) AS club
            FROM roster_players
            WHERE TRIM(COALESCE(club, '')) != ''
            ORDER BY club COLLATE NOCASE
            """
        ).fetchall()

        has_deleted = _table_exists(conn, "deleted_teams")
        for row in clubs:
            club = str(row["club"] or "").strip()
            if not club:
                continue

            if has_deleted:
                conn.execute(
                    "DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE",
                    (club,),
                )

            _upsert_catalog(conn, club, _country_for(club))


def _active_teams():
    _sync_loaded_teams_into_catalog()
    return _ORIGINAL_ACTIVE_TEAMS()


def _official_name(name):
    _sync_loaded_teams_into_catalog()
    return _ORIGINAL_OFFICIAL_NAME(name)


def apply_roster_catalog_autosync_patch(runtime, bot):
    """Install after the deletion/catalog guards have finished applying."""
    global _ORIGINAL_ACTIVE_TEAMS, _ORIGINAL_OFFICIAL_NAME

    if getattr(runtime, "_ajpa_roster_catalog_autosync_patch", False):
        return

    # Capture the FINAL tombstone-aware functions now, not at module import time.
    _ORIGINAL_ACTIVE_TEAMS = builder._active_teams
    _ORIGINAL_OFFICIAL_NAME = builder._official_name

    builder._active_teams = _active_teams
    builder._official_name = _official_name
    teams.official_name = _official_name

    # Force one repair immediately for the currently selected startup DB. Future
    # guilds are repaired lazily when their selector/official-name lookup runs.
    _sync_loaded_teams_into_catalog()

    runtime._ajpa_roster_catalog_autosync_patch = True
    print("AJPA catálogo reparador instalado DESPUÉS del guard de eliminación")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_catalog_autosync(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_roster_catalog_autosync_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_roster_catalog_autosync_wrapped",
    False,
):
    _apply_guild_isolation_then_catalog_autosync._ajpa_roster_catalog_autosync_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_catalog_autosync
