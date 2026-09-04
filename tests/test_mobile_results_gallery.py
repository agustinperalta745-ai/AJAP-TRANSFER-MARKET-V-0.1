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
        self.assertFalse(results[0]['is_classic'])
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM league_ges_result_queue').fetchone()[0], 3)
        conn.close()

    def test_excludes_only_four_rejected_cards_without_mutating_history(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE league_ges_result_queue (source_message_id INTEGER PRIMARY KEY, ges_message_id INTEGER, home_team TEXT, away_team TEXT, home_goals INTEGER, away_goals INTEGER, created_at TEXT)')
        rejected = [1543407517021896744, 1543406316846981231,
                    1543372234897236039, 1543370690369949697]
        rows = [(source, 11, 'Real Betis', 'Sevilla FC', 2, 0, '2026-08-29')
                for source in rejected]
        rows += [(1544535393939230751, 12, 'Real Betis', 'Sevilla FC', 2, 0, '2026-09-02'),
                 (1544535393939230752, 13, 'Ajax', 'Everton', 2, 1, '2026-09-02')]
        conn.executemany('INSERT INTO league_ges_result_queue VALUES (?,?,?,?,?,?,?)', rows)
        with patch.object(history.mobile_read_api, '_live_mobile_club_names', return_value=[]):
            results = history.result_cards_payload(conn)
        self.assertEqual({r['id'] for r in results},
                         {'1544535393939230751', '1544535393939230752'})
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM league_ges_result_queue').fetchone()[0], 6)
        conn.close()

    def test_classic_badge_only_during_rivalry_interval(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE league_ges_result_queue (source_message_id INTEGER PRIMARY KEY, ges_message_id INTEGER, home_team TEXT, away_team TEXT, home_goals INTEGER, away_goals INTEGER, created_at TEXT)')
        conn.execute('CREATE TABLE classic_rivals (id INTEGER PRIMARY KEY, club_a TEXT, club_b TEXT, accepted_at TEXT, active INTEGER, released_at TEXT)')
        conn.execute("INSERT INTO classic_rivals VALUES (1, 'Fulham', 'West Ham United', '2026-09-02 12:00:00', 0, '2026-09-04 12:00:00')")
        conn.executemany('INSERT INTO league_ges_result_queue VALUES (?,?,?,?,?,?,?)', [
            (101, 21, 'Fulham', 'West Ham United', 1, 0, '2026-09-01 20:00:00'),
            (102, 22, 'West Ham United', 'Fulham', 0, 4, '2026-09-03 20:00:00'),
            (103, 23, 'Fulham', 'West Ham United', 2, 1, '2026-09-05 20:00:00'),
        ])
        with patch.object(history.mobile_read_api, '_live_mobile_club_names', return_value=['Fulham', 'West Ham United']):
            results = history.result_cards_payload(conn)
        by_id = {r['id']: r for r in results}
        self.assertFalse(by_id['101']['is_classic'])
        self.assertTrue(by_id['102']['is_classic'])
        self.assertFalse(by_id['103']['is_classic'])
        conn.close()

    def test_legacy_database_fallback(self):
        conn = sqlite3.connect(':memory:')
        with patch.object(history, 'matches_payload', return_value=[{'id': 1}]) as fallback:
            self.assertEqual(history.result_cards_payload(conn), [{'id': 1}])
            fallback.assert_called_once_with(conn)
        conn.close()
