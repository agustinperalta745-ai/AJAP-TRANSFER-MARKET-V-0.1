import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import mobile_read_api as api


class MobileReadApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "ajap_test.db"
        os.environ["DB_PATH"] = str(self.db_path)
        os.environ["AJAP_LEGACY_GUILD_ID"] = "123"
        os.environ["AJPA_MOBILE_GUILD_ID"] = "123"

        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE league_teams (name TEXT PRIMARY KEY, active INTEGER NOT NULL);
                CREATE TABLE club_finances (club TEXT PRIMARY KEY, balance INTEGER NOT NULL);
                CREATE TABLE roster_players (
                    id INTEGER PRIMARY KEY, name TEXT, position TEXT, club TEXT,
                    rating INTEGER, min_sale_value INTEGER
                );
                CREATE TABLE publications (
                    id INTEGER PRIMARY KEY, player TEXT, position TEXT, club TEXT,
                    price TEXT, detail TEXT, active INTEGER, operation_type TEXT
                );
                CREATE TABLE market_state (id INTEGER PRIMARY KEY, is_open INTEGER, updated_at TEXT);
                CREATE TABLE seasons (id INTEGER PRIMARY KEY, name TEXT, active INTEGER);
                INSERT INTO league_teams VALUES ('Ajax', 1), ('Viejo FC', 0);
                INSERT INTO club_finances VALUES ('Ajax', 10000000);
                INSERT INTO roster_players VALUES
                    (1, 'Jugador A', 'CF', 'Ajax', 82, 10000000),
                    (2, 'Jugador Libre A', 'AMF', 'Jugador Libre', 80, 7500000);
                INSERT INTO publications VALUES
                    (1, 'Jugador A', 'CF', 'Ajax', '$12.000.000', 'Negociable', 1, 'TRANSFERENCIA'),
                    (2, 'Jugador Libre A', 'AMF', 'Jugador Libre', '$0', 'Liberado', 1, 'JUGADOR LIBRE');
                INSERT INTO market_state VALUES (1, 1, '2026-08-30 00:00:00');
                INSERT INTO seasons VALUES (1, 'Temporada 1', 1);
                """
            )

    def tearDown(self):
        self.temp.cleanup()

    def test_snapshot_reads_real_tables(self):
        with api.readonly_db() as conn:
            data = api.snapshot_payload(conn)
        self.assertTrue(data["read_only"])
        self.assertTrue(data["status"]["market_open"])
        ajax = next(club for club in data["clubs"] if club["name"] == "Ajax")
        self.assertEqual(ajax, {"name": "Ajax", "balance": 10000000, "roster_count": 1})
        self.assertNotIn("Viejo FC", {club["name"] for club in data["clubs"]})
        self.assertEqual(len(data["market"]), 2)
        self.assertEqual(len(data["free_agents"]), 1)
        self.assertEqual(data["free_agents"][0]["player"], "Jugador Libre A")

    def test_roster_exposes_ovr_and_value(self):
        with api.readonly_db() as conn:
            players = api.roster_payload(conn, "Ajax")
        self.assertEqual(players[0]["code"], "AJAP-000001")
        self.assertEqual(players[0]["ovr"], 82)
        self.assertEqual(players[0]["market_value"], 10000000)

    def test_sqlite_connection_rejects_writes(self):
        with api.readonly_db() as conn:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("INSERT INTO league_teams VALUES ('Intruso', 1)")


if __name__ == "__main__":
    unittest.main()
