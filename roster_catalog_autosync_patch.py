"""Keep the selectable team catalog in sync with loaded rosters.

AJPA rule: if a club currently has players in roster_players, that club is a loaded
team and must be selectable. JSON/seed roster imports therefore also register (or
reactivate) the club in league_teams and create its finance row when missing.

The Staff delete flow removes the club roster before writing its deleted_teams
tombstone. Because of that, finding players for a tombstoned club means the team
was deliberately loaded again later; in that case the tombstone is cleared and
the club becomes selectable again.
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

        has_deleted = _table_exists(conn, "deleted_teams")

        for row in clubs:
            club = str(row["club"]).strip()
            if not club:
                continue

            # A loaded roster is now the source of truth for team availability.
            # The delete flow removes roster_players, so if players exist again,
            # the team has been intentionally reloaded and any old tombstone is stale.
            if has_deleted:
                conn.execute(
                    "DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE",
                    (club,),
                )

            existing = conn.execute(
                "SELECT country FROM league_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
                (club,),
            ).fetchone()
            country = (
                str(existing["country"] or "").strip()
                if existing and str(existing["country"] or "").strip()
                else _country_for(club)
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
                (club, country),
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
# Assignment callbacks resolve this function from team_assignment itself, so keep
# that path synchronized too.
teams.official_name = _official_name

print("AJPA catálogo automático activo: toda plantilla cargada queda seleccionable")
