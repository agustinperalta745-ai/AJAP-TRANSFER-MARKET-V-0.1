"""Keep the selectable team catalog in sync with loaded rosters.

From now on, any club that already has players in roster_players is automatically
registered in league_teams if it is missing there. Existing inactive teams are
left inactive, so an intentional Staff deletion/deactivation is not undone.

This makes JSON/seed roster loads behave like a complete team load: the club is
selectable and receives the standard initial budget if it had no finance row yet.
"""

from __future__ import annotations

import admin_roster_builder_patch as builder
import team_assignment as teams


_original_active_teams = builder._active_teams
_original_official_name = builder._official_name


def _country_for(club: str) -> str:
    wanted = str(club or "").strip().casefold()
    for name, country in getattr(teams, "OFFICIAL_TEAMS", []):
        if str(name).strip().casefold() == wanted:
            return str(country or "Sin definir")
    return "Sin definir"


def _sync_roster_clubs_into_catalog():
    app = builder.APP
    if app is None:
        return

    builder._ensure_schema()
    with app.db() as conn:
        clubs = conn.execute(
            """
            SELECT DISTINCT TRIM(club) AS club
            FROM roster_players
            WHERE TRIM(COALESCE(club, '')) != ''
            ORDER BY club COLLATE NOCASE
            """
        ).fetchall()

        for row in clubs:
            club = str(row["club"]).strip()
            existing = conn.execute(
                "SELECT id FROM league_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
                (club,),
            ).fetchone()

            # Only create missing catalog rows. Never reactivate an intentionally
            # inactive/deleted team merely because stale roster data exists.
            if not existing:
                conn.execute(
                    """
                    INSERT INTO league_teams (name, country, active)
                    VALUES (?, ?, 1)
                    """,
                    (club, _country_for(club)),
                )

            conn.execute(
                """
                INSERT OR IGNORE INTO club_finances (club, balance, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (club, builder.INITIAL_TEAM_BUDGET),
            )


def _active_teams():
    _sync_roster_clubs_into_catalog()
    return _original_active_teams()


def _official_name(name):
    _sync_roster_clubs_into_catalog()
    return _original_official_name(name)


builder._active_teams = _active_teams
builder._official_name = _official_name

print("AJPA catálogo automático activo: toda plantilla cargada crea equipo seleccionable")
