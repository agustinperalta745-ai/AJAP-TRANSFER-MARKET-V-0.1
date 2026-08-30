import os
import sqlite3
import unittest
from unittest.mock import patch

import mobile_auth as auth


class MobileAuthTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE clubs (user_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE club_assignment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                club TEXT NOT NULL,
                action TEXT NOT NULL
            );
            CREATE TABLE club_assignment_guard (
                user_id INTEGER PRIMARY KEY,
                club TEXT,
                active INTEGER NOT NULL
            );
            CREATE TABLE deleted_teams (name TEXT PRIMARY KEY);
            CREATE TABLE club_finances (club TEXT PRIMARY KEY, balance INTEGER NOT NULL);
            CREATE TABLE roster_players (id INTEGER PRIMARY KEY, name TEXT, club TEXT);
            """
        )
        os.environ["DISCORD_CLIENT_ID"] = "1541608838032265238"
        os.environ["AJPA_MOBILE_GUILD_ID"] = "1501062815920816360"

    def tearDown(self):
        self.conn.close()

    def test_live_club_wins_old_positive_history(self):
        self.conn.execute("INSERT INTO clubs VALUES (?, ?)", (10, "Aston Villa"))
        self.conn.execute(
            "INSERT INTO club_assignment_history (user_id, club, action) VALUES (?, ?, ?)",
            (10, "Ajax", "ASIGNADO"),
        )
        self.assertEqual(auth.resolve_club_readonly(self.conn, 10), "Aston Villa")

    def test_resignation_is_authoritative(self):
        self.conn.execute("INSERT INTO clubs VALUES (?, ?)", (11, "Ajax"))
        self.conn.execute(
            "INSERT INTO club_assignment_history (user_id, club, action) VALUES (?, ?, ?)",
            (11, "Ajax", "RENUNCIA_DT"),
        )
        self.assertIsNone(auth.resolve_club_readonly(self.conn, 11))

    def test_profile_uses_same_club_finance_and_roster(self):
        self.conn.execute("INSERT INTO clubs VALUES (?, ?)", (12, "Ajax"))
        self.conn.execute("INSERT INTO club_finances VALUES (?, ?)", ("Ajax", 10000000))
        self.conn.executemany(
            "INSERT INTO roster_players VALUES (?, ?, ?)",
            [(1, "Jugador A", "Ajax"), (2, "Jugador B", "Ajax")],
        )
        identity = {
            "user": {"id": "12", "username": "dt", "global_name": "DT", "avatar": None},
            "guild": {"id": "1501062815920816360", "in_guild": True, "is_staff": False},
        }
        data = auth.profile_payload(self.conn, identity)
        self.assertEqual(data["club"], "Ajax")
        self.assertEqual(data["balance"], 10000000)
        self.assertEqual(data["roster_count"], 2)
        self.assertFalse(data["is_staff"])
        self.assertTrue(data["read_only"])

    @patch("mobile_auth._discord_get")
    def test_discord_identity_validates_guild_and_admin(self, discord_get):
        discord_get.side_effect = [
            {
                "application": {"id": "1541608838032265238"},
                "scopes": ["identify", "guilds"],
                "user": {
                    "id": "99",
                    "username": "admin",
                    "global_name": "Admin",
                    "avatar": "hash",
                },
            },
            [
                {
                    "id": "1501062815920816360",
                    "owner": False,
                    "permissions": "8",
                }
            ],
        ]
        identity = auth.discord_identity("Bearer token-de-prueba")
        self.assertEqual(identity["user"]["id"], "99")
        self.assertTrue(identity["guild"]["in_guild"])
        self.assertTrue(identity["guild"]["is_staff"])

    def test_missing_bearer_is_rejected(self):
        with self.assertRaises(auth.OAuthError):
            auth.discord_identity(None)


if __name__ == "__main__":
    unittest.main()
