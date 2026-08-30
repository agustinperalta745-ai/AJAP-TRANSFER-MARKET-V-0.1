import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import mobile_write_api as api


class MobileWriteApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "ajap_write_test.db"
        os.environ["DB_PATH"] = str(self.db_path)
        os.environ["AJAP_LEGACY_GUILD_ID"] = "123"
        os.environ["AJPA_MOBILE_GUILD_ID"] = "123"

        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE clubs (user_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE roster_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    position TEXT NOT NULL,
                    club TEXT NOT NULL,
                    rating INTEGER,
                    min_sale_value INTEGER,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE publications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player TEXT NOT NULL,
                    position TEXT NOT NULL,
                    club TEXT NOT NULL,
                    price TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    owner_id INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    operation_type TEXT NOT NULL DEFAULT 'TRANSFERENCIA',
                    season_id INTEGER,
                    loan_seasons INTEGER,
                    purchase_option_enabled INTEGER,
                    purchase_option_value TEXT
                );
                CREATE TABLE offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    publication_id INTEGER NOT NULL,
                    player TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    message TEXT NOT NULL,
                    from_id INTEGER NOT NULL,
                    from_club TEXT NOT NULL,
                    to_id INTEGER NOT NULL,
                    to_club TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDIENTE',
                    operation_type TEXT NOT NULL DEFAULT 'TRANSFERENCIA',
                    season_id INTEGER,
                    offer_kind TEXT NOT NULL DEFAULT 'DINERO',
                    offered_player_id INTEGER,
                    offered_player TEXT
                );
                CREATE TABLE transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player TEXT NOT NULL,
                    seller TEXT NOT NULL,
                    buyer TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    offer_id INTEGER NOT NULL,
                    player_id INTEGER,
                    operation_type TEXT NOT NULL DEFAULT 'TRANSFERENCIA',
                    season_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'PENDIENTE_ADMIN',
                    notes TEXT,
                    deal_group TEXT
                );
                CREATE TABLE market_state (id INTEGER PRIMARY KEY, is_open INTEGER NOT NULL);
                CREATE TABLE seasons (id INTEGER PRIMARY KEY, name TEXT, active INTEGER);
                CREATE TABLE club_finances (club TEXT PRIMARY KEY COLLATE NOCASE, balance INTEGER NOT NULL);
                CREATE TABLE player_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER, player TEXT, from_club TEXT, to_club TEXT,
                    transfer_id INTEGER, season_id INTEGER, event_type TEXT
                );

                INSERT INTO clubs VALUES (1001, 'Ajax'), (2002, 'Aston Villa');
                INSERT INTO market_state VALUES (1, 1);
                INSERT INTO seasons VALUES (1, 'Temporada 1', 1);
                INSERT INTO club_finances VALUES ('Ajax', 10000000), ('Aston Villa', 10000000);
                """
            )
            # Ajax has 21 active players so it may sell/release one.
            for i in range(1, 22):
                conn.execute(
                    "INSERT INTO roster_players(name,position,club,rating,min_sale_value) VALUES(?,?,?,?,?)",
                    (f"Ajax {i}", "CF", "Ajax", 75, 1500000),
                )
            # Aston Villa has 20 active players.
            for i in range(1, 21):
                conn.execute(
                    "INSERT INTO roster_players(name,position,club,rating,min_sale_value) VALUES(?,?,?,?,?)",
                    (f"Villa {i}", "CMF", "Aston Villa", 75, 1500000),
                )

    def tearDown(self):
        self.temp.cleanup()

    def test_pair_code_is_one_time_and_returns_session(self):
        code = api.issue_pair_code(api.write_db, 1001)
        self.assertEqual(len(code), 8)
        result = api.exchange_pair_code(code)
        self.assertTrue(result["token"])
        self.assertEqual(result["profile"]["club"], "Ajax")
        with self.assertRaises(api.ApiFailure):
            api.exchange_pair_code(code)

    def test_publish_offer_accept_creates_staff_pending_transfer(self):
        with api.write_db() as conn:
            api.ensure_schema(conn)
            player = conn.execute("SELECT id FROM roster_players WHERE name='Ajax 1'").fetchone()
            publication = api.create_publication(
                conn,
                {"user_id": 1001, "is_staff": False},
                {
                    "player_id": player["id"],
                    "operation_type": "TRANSFERENCIA",
                    "price": "1500000",
                    "detail": "Negociable",
                },
            )
            offer = api.create_offer(
                conn,
                {"user_id": 2002, "is_staff": False},
                publication["publication_id"],
                {"amount": "1500000", "message": "Oferta app"},
            )
            decision = api.decide_offer(
                conn,
                {"user_id": 1001, "is_staff": False},
                offer["offer_id"],
                True,
            )
            conn.commit()
            self.assertEqual(decision["status"], "ACEPTADA")
            transfer = conn.execute("SELECT * FROM transfers WHERE id=?", (decision["transfer_ids"][0],)).fetchone()
            self.assertEqual(transfer["status"], "PENDIENTE_ADMIN")
            self.assertEqual(transfer["seller"], "Ajax")
            self.assertEqual(transfer["buyer"], "Aston Villa")

    def test_release_charges_20_percent_and_creates_free_listing(self):
        with api.write_db() as conn:
            api.ensure_schema(conn)
            player = conn.execute("SELECT id FROM roster_players WHERE name='Ajax 2'").fetchone()
            result = api.release_player(
                conn,
                {"user_id": 1001, "is_staff": False},
                player["id"],
            )
            conn.commit()
            self.assertEqual(result["cost"], 300000)
            released = conn.execute("SELECT club FROM roster_players WHERE id=?", (player["id"],)).fetchone()
            self.assertEqual(released["club"], "Jugador Libre")
            listing = conn.execute("SELECT * FROM publications WHERE id=?", (result["publication_id"],)).fetchone()
            self.assertEqual(listing["price"], "$0")
            self.assertEqual(listing["operation_type"], "JUGADOR LIBRE")


if __name__ == "__main__":
    unittest.main()
