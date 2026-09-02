import sqlite3
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
