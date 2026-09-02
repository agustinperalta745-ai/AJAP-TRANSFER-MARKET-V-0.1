import sqlite3
import unittest
from unittest.mock import patch

import mobile_competition_cycle_api_patch as competition
import mobile_league_history_api_patch as history


class MobileLeagueHistoryPayloadTests(unittest.TestCase):
    def connection(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        return conn

    def test_empty_without_league_matches(self):
        conn = self.connection()
        try:
            self.assertEqual(history.matches_payload(conn), [])
        finally:
            conn.close()

    def test_returns_latest_official_matches_and_canonical_mobile_names(self):
        conn = self.connection()
        try:
            conn.execute(
                """
                CREATE TABLE league_matches (
                    id INTEGER PRIMARY KEY,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    home_goals INTEGER NOT NULL,
                    away_goals INTEGER NOT NULL,
                    created_at DATETIME
                )
                """
            )
            conn.execute(
                "INSERT INTO league_matches VALUES (1, 'Sevilla', 'Real Betis', 2, 0, '2026-09-01 18:00:00')"
            )
            conn.execute(
                "INSERT INTO league_matches VALUES (2, 'Villarreal', 'Everton', 1, 1, '2026-09-01 19:00:00')"
            )
            conn.commit()

            with patch.object(
                history.mobile_read_api,
                "_live_mobile_club_names",
                return_value=["Sevilla FC", "Real Betis", "Villarreal CF", "Everton"],
            ):
                payload = history.matches_payload(conn)

            self.assertEqual([row["id"] for row in payload], [2, 1])
            self.assertEqual(payload[0]["home_team"], "Villarreal CF")
            self.assertEqual(payload[0]["away_team"], "Everton")
            self.assertEqual(payload[0]["home_goals"], 1)
            self.assertEqual(payload[0]["away_goals"], 1)
            self.assertEqual(payload[1]["home_team"], "Sevilla FC")
            self.assertEqual(payload[1]["away_team"], "Real Betis")
        finally:
            conn.close()

    def test_cycle_filter_is_safe_on_readonly_league_connection(self):
        conn = self.connection()
        try:
            conn.executescript(
                """
                CREATE TABLE competition_cycle_state (
                    id INTEGER PRIMARY KEY,
                    phase TEXT NOT NULL,
                    season_number INTEGER NOT NULL,
                    competition_id INTEGER,
                    updated_at DATETIME
                );
                INSERT INTO competition_cycle_state
                    (id, phase, season_number, competition_id, updated_at)
                VALUES (1, 'season', 1, 7, '2026-09-02 12:00:00');

                CREATE TABLE competition_editions (
                    id INTEGER PRIMARY KEY,
                    kind TEXT NOT NULL,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                INSERT INTO competition_editions VALUES (7, 'season', 'Temporada 1', 'active');

                CREATE TABLE market_state (id INTEGER PRIMARY KEY, is_open INTEGER NOT NULL);
                INSERT INTO market_state VALUES (1, 0);

                CREATE TABLE league_matches (
                    id INTEGER PRIMARY KEY,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    home_goals INTEGER NOT NULL,
                    away_goals INTEGER NOT NULL,
                    competition_id INTEGER
                );
                INSERT INTO league_matches VALUES (1, 'Monaco', 'Ajax', 2, 1, 7);
                INSERT INTO league_matches VALUES (2, 'Monaco', 'Ajax', 0, 4, 6);
                """
            )
            conn.commit()
            conn.execute("PRAGMA query_only = ON")

            base = {
                "standings": [],
                "scorers": [],
                "matches": [
                    {"id": 2, "home_team": "Monaco", "away_team": "Ajax", "home_goals": 0, "away_goals": 4},
                    {"id": 1, "home_team": "Monaco", "away_team": "Ajax", "home_goals": 2, "away_goals": 1},
                ],
            }
            with patch.object(
                competition.mobile_read_api,
                "_live_mobile_club_names",
                return_value=["Monaco", "Ajax"],
            ):
                payload = competition._filtered_league_payload(conn, base)

            by_team = {row["team"]: row for row in payload["standings"]}
            self.assertEqual(by_team["Monaco"]["pts"], 3)
            self.assertEqual(by_team["Monaco"]["gf"], 2)
            self.assertEqual(by_team["Ajax"]["pts"], 0)
            self.assertEqual(payload["matches"], base["matches"])
            self.assertEqual(payload["cycle"]["competition_id"], 7)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
