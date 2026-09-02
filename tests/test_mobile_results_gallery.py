import sqlite3
import unittest
from unittest.mock import patch
import mobile_league_history_api_patch as history

class ResultGalleryTests(unittest.TestCase):
    def test_only_posted_results_and_large_discord_ids_preserved(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE league_ges_result_queue (source_message_id INTEGER PRIMARY KEY, ges_message_id INTEGER, home_team TEXT, away_team TEXT, home_goals INTEGER, away_goals INTEGER, created_at TEXT)')
        conn.executemany('INSERT INTO league_ges_result_queue VALUES (?,?,?,?,?,?,?)', [
            (1541817856008650844, 11, 'Ajax', 'Everton', 2, 1, '2026-09-01'),
            (1541817856008650845, None, 'Ajax', 'Everton', 9, 9, '2026-09-02'),
            (1541817856008650846, 12, 'Everton', 'Ajax', 2, 3, '2026-09-02'),
        ])
        with patch.object(history.mobile_read_api, '_live_mobile_club_names', return_value=[]):
            results = history.result_cards_payload(conn)
        self.assertEqual([r['id'] for r in results], ['1541817856008650846','1541817856008650844'])
        self.assertEqual(results[1]['home_goals'], 2)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM league_ges_result_queue').fetchone()[0], 3)
        conn.close()

    def test_legacy_database_fallback(self):
        conn = sqlite3.connect(':memory:')
        with patch.object(history, 'matches_payload', return_value=[{'id': 1}]) as fallback:
            self.assertEqual(history.result_cards_payload(conn), [{'id': 1}])
            fallback.assert_called_once_with(conn)
        conn.close()
