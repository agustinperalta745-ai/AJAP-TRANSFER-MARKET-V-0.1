import sqlite3
import unittest
from unittest.mock import patch

import mobile_match_search_patch as match_search


class MobileMatchSearchPatchTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE league_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_message_id INTEGER NOT NULL UNIQUE,
                source_channel_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                home_goals INTEGER NOT NULL,
                away_goals INTEGER NOT NULL,
                confidence REAL NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        match_search._ensure_schema(self.conn)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _create(self, club: str, user_id: int):
        with patch.object(match_search.mobile_write_api, "_require_club", return_value=club):
            result = match_search.create_search(
                self.conn,
                {"user_id": user_id},
                {
                    "pes_lobby": "Vesti 1",
                    "room_name": f"AJPA {club}",
                    "password": "",
                },
            )
        self.conn.commit()
        return result

    def test_open_search_expires_after_thirty_minutes(self):
        self.conn.execute(
            """
            INSERT INTO mobile_match_searches
                (creator_user_id, creator_club, pes_lobby, room_name, status, created_at)
            VALUES (1, 'Ajax', 'Vesti 1', 'AJPA Ajax', 'OPEN', datetime('now', '-31 minutes'))
            """
        )
        match_search._expire_stale_open(self.conn)
        row = self.conn.execute(
            "SELECT status, expired_at FROM mobile_match_searches LIMIT 1"
        ).fetchone()
        self.assertEqual(row["status"], match_search.EXPIRED)
        self.assertIsNotNone(row["expired_at"])

    def test_second_eligible_search_is_auto_paired(self):
        first = self._create("Ajax", 1001)
        self.assertEqual(first["status"], match_search.OPEN)

        second = self._create("Aston Villa", 2002)
        self.assertEqual(second["status"], match_search.MATCHED)
        self.assertTrue(second["auto_matched"])
        self.assertEqual(second["creator_club"], "Ajax")
        self.assertEqual(second["opponent_club"], "Aston Villa")
        self.assertEqual(second["room_access"]["room_name"], "AJPA Ajax")

        rows = self.conn.execute(
            "SELECT creator_club, opponent_club, status FROM mobile_match_searches"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], match_search.MATCHED)

    def test_already_played_clubs_are_not_auto_paired(self):
        self.conn.execute(
            """
            INSERT INTO league_matches
                (source_message_id, source_channel_id, author_id, home_team, away_team,
                 home_goals, away_goals, confidence)
            VALUES (99, 1, 1, 'Ajax', 'Aston Villa', 2, 1, 0.99)
            """
        )
        self.conn.commit()
        first = self._create("Ajax", 1001)
        second = self._create("Aston Villa", 2002)
        self.assertEqual(first["status"], match_search.OPEN)
        self.assertEqual(second["status"], match_search.OPEN)
        count = self.conn.execute(
            "SELECT COUNT(*) FROM mobile_match_searches WHERE status='OPEN'"
        ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_bot_result_turns_matched_card_into_completed_score(self):
        self.conn.execute(
            """
            INSERT INTO mobile_match_searches
                (creator_user_id, creator_club, pes_lobby, room_name, status,
                 opponent_user_id, opponent_club, matched_at)
            VALUES (1, 'Feyenoord', 'Vesti 1', 'AJPA', 'MATCHED', 2, 'Manchester City', CURRENT_TIMESTAMP)
            """
        )
        self.conn.execute(
            """
            INSERT INTO league_matches
                (source_message_id, source_channel_id, author_id, home_team, away_team,
                 home_goals, away_goals, confidence)
            VALUES (12345, 1, 1, 'Manchester City', 'Feyenoord', 3, 2, 0.99)
            """
        )
        self.conn.commit()

        match_search._reconcile_completed(self.conn)
        row = self.conn.execute(
            """
            SELECT status, result_home_team, result_away_team,
                   result_home_goals, result_away_goals
            FROM mobile_match_searches LIMIT 1
            """
        ).fetchone()
        self.assertEqual(row["status"], match_search.COMPLETED)
        self.assertEqual(row["result_home_team"], "Manchester City")
        self.assertEqual(row["result_away_team"], "Feyenoord")
        self.assertEqual(row["result_home_goals"], 3)
        self.assertEqual(row["result_away_goals"], 2)


if __name__ == "__main__":
    unittest.main()
