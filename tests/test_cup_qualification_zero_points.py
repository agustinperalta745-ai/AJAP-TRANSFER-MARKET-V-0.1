import sqlite3
import unittest
from unittest.mock import patch

import mobile_cup_tournaments_api_patch as cups


class CupQualificationZeroPointTableTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE competition_editions (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                season_number INTEGER NOT NULL,
                final_snapshot_json TEXT
            );
            CREATE TABLE league_ges_competition_config (
                competition_id INTEGER PRIMARY KEY,
                competition_label TEXT NOT NULL,
                league_id TEXT NOT NULL,
                classification_url TEXT NOT NULL,
                results_url TEXT NOT NULL,
                scorers_url TEXT NOT NULL
            );
            CREATE TABLE league_ges_standings (
                guild_id INTEGER NOT NULL,
                league_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                team TEXT NOT NULL,
                pts INTEGER NOT NULL,
                pj INTEGER NOT NULL,
                pg INTEGER NOT NULL,
                pe INTEGER NOT NULL,
                pp INTEGER NOT NULL,
                gf INTEGER NOT NULL,
                gc INTEGER NOT NULL,
                dg INTEGER NOT NULL,
                PRIMARY KEY (guild_id, league_id, team)
            );
            """
        )
        self.conn.execute(
            "INSERT INTO competition_editions(id,kind,season_number) VALUES(77,'season',1)"
        )
        self.conn.execute(
            """INSERT INTO league_ges_competition_config(
                   competition_id,competition_label,league_id,
                   classification_url,results_url,scorers_url
               ) VALUES(77,'Temporada 1','GES-TEST','c','r','s')"""
        )
        self.teams = [f"Equipo {index:02d}" for index in range(1, 25)]
        for position, team in enumerate(self.teams, start=1):
            self.conn.execute(
                """INSERT INTO league_ges_standings(
                       guild_id,league_id,position,team,
                       pts,pj,pg,pe,pp,gf,gc,dg
                   ) VALUES(1,'GES-TEST',?,?,0,0,0,0,0,0,0,0)""",
                (position, team),
            )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_load_from_table_uses_positions_even_when_everyone_has_zero_points(self):
        # Reverse the catalog deliberately: the explicit GES position must win.
        with patch.object(
            cups.mobile_read_api,
            "_live_mobile_club_names",
            return_value=list(reversed(self.teams)),
        ):
            suggestion = cups.qualification_suggestion(self.conn, 1)

        self.assertEqual(suggestion["champions"], self.teams[:16])
        self.assertEqual(suggestion["europa"], self.teams[16:24])
        self.assertEqual(len(suggestion["champions"]), 16)
        self.assertEqual(len(suggestion["europa"]), 8)
        self.assertEqual(suggestion["warnings"], [])

    def test_partial_table_is_completed_with_active_zero_match_clubs(self):
        self.conn.execute(
            "DELETE FROM league_ges_standings WHERE position > 3"
        )
        self.conn.commit()

        active = self.teams
        with patch.object(
            cups.mobile_read_api,
            "_live_mobile_club_names",
            return_value=active,
        ):
            standings = cups._season_standings(self.conn, 1)

        self.assertEqual(len(standings), 24)
        self.assertEqual([row["team"] for row in standings[:3]], self.teams[:3])
        self.assertTrue(all(int(row["pts"]) == 0 for row in standings))
        self.assertTrue(all(int(row["pj"]) == 0 for row in standings))


if __name__ == "__main__":
    unittest.main()
