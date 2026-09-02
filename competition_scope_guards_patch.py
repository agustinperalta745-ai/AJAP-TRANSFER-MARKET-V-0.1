"""Keep fixture eligibility per competition while classic history stays all-time.

This patch intentionally runs after league_admin_config_location_patch, whose
single/double-round policy remains authoritative. Only the data slice changes:
old-season matches no longer block a new season, and Buscar Partido is disabled
while a market window is active.
"""

from __future__ import annotations

import sqlite3

import competition_cycle as cycle
import league_admin_config_location_patch as config
import league_result_evidence_patch as evidence


def _active_cid(conn: sqlite3.Connection):
    cycle.ensure_schema(conn)
    return cycle.active_competition_id(conn)


def _existing_official_pair_current(
    runtime,
    guild_id: int,
    home: str,
    away: str,
    exclude_source=None,
):
    conn = config.league_ui.league.db(runtime, int(guild_id))
    try:
        config._ensure_season_schema_conn(conn)
        cid = _active_cid(conn)
        if cid is None:
            return None
        limit = config._allowed_legs_from_conn(conn)
        rows = conn.execute(
            """
            SELECT * FROM league_matches
            WHERE competition_id=?
              AND ((home_team=? AND away_team=?) OR (home_team=? AND away_team=?))
            ORDER BY id DESC
            """,
            (int(cid), home, away, away, home),
        ).fetchall()
        valid = [
            row
            for row in rows
            if exclude_source is None
            or int(row["source_message_id"]) != int(exclude_source)
        ]
        return valid[0] if len(valid) >= limit else None
    finally:
        conn.close()


evidence._existing_official_pair = _existing_official_pair_current


mobile = config.mobile_match_search
if mobile is not None:
    _original_create_search = mobile.create_search
    _original_join_search = mobile.join_search
    _original_eligibility = mobile._eligibility

    def _phase(conn: sqlite3.Connection) -> str:
        cycle.ensure_schema(conn)
        row = conn.execute(
            "SELECT phase FROM competition_cycle_state WHERE id=1"
        ).fetchone()
        return str(row["phase"]) if row else cycle.PRESEASON

    def _require_playable(conn: sqlite3.Connection) -> None:
        phase = _phase(conn)
        if phase in cycle.PLAYABLE:
            return
        label = "Mercado 1" if phase == cycle.MARKET_1 else "Mercado 2"
        raise mobile.mobile_write_api.ApiFailure(
            f"Buscar Partido está pausado durante {label}. Se habilita en la próxima competencia.",
            409,
        )

    def _mobile_pair_result_count(conn: sqlite3.Connection, club_a: str, club_b: str) -> int:
        if not mobile.mobile_write_api._table_exists(conn, "league_matches"):
            return 0
        cid = _active_cid(conn)
        if cid is None:
            return 0
        a, b = mobile._norm_team(club_a), mobile._norm_team(club_b)
        count = 0
        rows = conn.execute(
            "SELECT home_team,away_team FROM league_matches WHERE competition_id=?",
            (int(cid),),
        ).fetchall()
        for row in rows:
            home, away = mobile._norm_team(row["home_team"]), mobile._norm_team(row["away_team"])
            if {home, away} == {a, b}:
                count += 1
        return count

    def _already_played_current(conn: sqlite3.Connection, club_a: str, club_b: str) -> bool:
        return _mobile_pair_result_count(conn, club_a, club_b) >= config._allowed_legs_from_conn(conn)

    def _official_result_after_current(
        conn: sqlite3.Connection,
        club_a: str,
        club_b: str,
        matched_at,
    ):
        if not mobile.mobile_write_api._table_exists(conn, "league_matches"):
            return None
        cid = _active_cid(conn)
        if cid is None:
            return None
        a, b = mobile._norm_team(club_a), mobile._norm_team(club_b)
        if matched_at:
            rows = conn.execute(
                """
                SELECT id,source_message_id,home_team,away_team,
                       home_goals,away_goals,created_at
                FROM league_matches
                WHERE competition_id=? AND datetime(created_at) >= datetime(?)
                ORDER BY id DESC
                """,
                (int(cid), str(matched_at)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id,source_message_id,home_team,away_team,
                       home_goals,away_goals,created_at
                FROM league_matches
                WHERE competition_id=?
                ORDER BY id DESC
                """,
                (int(cid),),
            ).fetchall()
        for row in rows:
            home, away = mobile._norm_team(row["home_team"]), mobile._norm_team(row["away_team"])
            if {home, away} == {a, b}:
                return row
        return None

    def _reconcile_completed_current(conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT id,status,creator_club,opponent_club,matched_at
            FROM mobile_match_searches
            WHERE opponent_club IS NOT NULL
              AND (status='MATCHED' OR (status='COMPLETED' AND result_home_goals IS NULL))
            """
        ).fetchall()
        for row in rows:
            result = _official_result_after_current(
                conn,
                str(row["creator_club"]),
                str(row["opponent_club"]),
                row["matched_at"],
            )
            if not result:
                continue
            conn.execute(
                """
                UPDATE mobile_match_searches
                SET status='COMPLETED',
                    completed_at=COALESCE(completed_at,CURRENT_TIMESTAMP),
                    result_home_team=?,result_away_team=?,
                    result_home_goals=?,result_away_goals=?,
                    result_source_message_id=?
                WHERE id=? AND status IN ('MATCHED','COMPLETED')
                """,
                (
                    str(result["home_team"]),
                    str(result["away_team"]),
                    int(result["home_goals"]),
                    int(result["away_goals"]),
                    int(result["source_message_id"]),
                    int(row["id"]),
                ),
            )

    def _eligibility_current(conn, viewer_club, creator_club):
        if _phase(conn) not in cycle.PLAYABLE:
            return False, "Buscar Partido está pausado mientras el mercado está abierto."
        return _original_eligibility(conn, viewer_club, creator_club)

    def _create_search_current(conn, session, payload):
        _require_playable(conn)
        return _original_create_search(conn, session, payload)

    def _join_search_current(conn, session, search_id):
        _require_playable(conn)
        return _original_join_search(conn, session, search_id)

    mobile._already_played = _already_played_current
    mobile._reconcile_completed = _reconcile_completed_current
    mobile._eligibility = _eligibility_current
    mobile.create_search = _create_search_current
    mobile.join_search = _join_search_current


print("AJPA fixture: cruces por competencia • clásicos históricos intactos • mercados sin Buscar Partido")
