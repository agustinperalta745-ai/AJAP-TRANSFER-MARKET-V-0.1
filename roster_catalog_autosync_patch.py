"""Keep the selectable team catalog in sync with loaded rosters.

AJPA rule: every team that is actually loaded must be selectable. We rebuild the
catalog on demand from two safe sources:
- current roster_players clubs (JSON/seed/admin-loaded teams), and
- the built-in OFFICIAL_TEAMS fallback, so an older guild database with an empty
  league_teams table cannot render "no active teams" after a deploy.

Staff-deleted teams remain hidden unless a roster for that club exists again. A
new roster is treated as an intentional reload and clears the old tombstone.
"""

from __future__ import annotations

import admin_roster_builder_patch as builder
import team_assignment as teams


# bot.py imports this module after admin_team_delete_patch, so these are the final
# tombstone-aware catalog functions. We sync first and then delegate to them.
_original_active_teams = builder._active_teams
_original_official_name = builder._official_name


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


def _sync_roster_clubs_into_catalog():
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
    _sync_roster_clubs_into_catalog()
    return _original_active_teams()


def _official_name(name):
    _sync_roster_clubs_into_catalog()
    return _original_official_name(name)


builder._active_teams = _active_teams
builder._official_name = _official_name
# Assignment callbacks resolve this function from team_assignment itself, so keep
# that path synchronized too.
teams.official_name = _official_name

print("AJPA catálogo reparador activo: equipos oficiales + plantillas siempre seleccionables")
