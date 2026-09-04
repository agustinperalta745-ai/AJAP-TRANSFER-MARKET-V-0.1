import sqlite3
import unittest
from unittest.mock import patch

import mobile_league_history_api_patch as history


class MobileLeagueHistoryTeamAliasTests(unittest.TestCase):
    def connection(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
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
        return conn

    def test_known_fulham_typo_is_exposed_as_canonical_fulham(self):
        conn = self.connection()
        try:
            conn.execute(
                "INSERT INTO league_matches VALUES (1, 'Porto', 'Fullam', 0, 2, '2026-09-04 18:00:00')"
            )
            conn.commit()
            with patch.object(
                history.mobile_read_api,
                "_live_mobile_club_names",
                return_value=["Porto", "Fulham"],
            ):
                payload = history.matches_payload(conn)

            self.assertEqual(payload[0]["home_team"], "Porto")
            self.assertEqual(payload[0]["away_team"], "Fulham")
        finally:
            conn.close()

    def test_fc_suffix_does_not_hide_match_from_club_history(self):
        conn = self.connection()
        try:
            conn.execute(
                "INSERT INTO league_matches VALUES (1, 'Porto', 'Fulham FC', 1, 1, '2026-09-04 18:00:00')"
            )
            conn.commit()
            with patch.object(
                history.mobile_read_api,
                "_live_mobile_club_names",
                return_value=["Porto", "Fulham"],
            ):
                payload = history.matches_payload(conn)

            self.assertEqual(payload[0]["away_team"], "Fulham")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
