import sqlite3
import unittest

import mobile_cup_tournaments_api_patch as cups


class ChampionsDropToEuropaTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        cups.ensure_schema(self.conn)
        cur = self.conn.execute(
            """INSERT INTO cup_tournament_editions(
                   season_number,status,champions_started_at,started_at
               ) VALUES(1,'ACTIVE',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""
        )
        self.edition_id = int(cur.lastrowid)

        for index in range(8):
            cups._insert_match(
                self.conn,
                self.edition_id,
                cups.CHAMPIONS,
                "R16",
                0,
                index,
                f"Champions A{index}",
                f"Champions B{index}",
                "Preclasificado Champions",
                "Preclasificado Champions",
            )
        cups._ensure_blank_bracket(self.conn, self.edition_id)

    def tearDown(self):
        self.conn.close()

    def test_finished_champions_loser_is_backfilled_into_europa(self):
        self.conn.execute(
            """UPDATE cup_matches
               SET home_goals=2,away_goals=0,winner_team='Champions A0',
                   loser_team='Champions B0',status='FINISHED'
               WHERE edition_id=? AND competition='champions'
                 AND round_key='R16' AND match_index=0""",
            (self.edition_id,),
        )

        changed = cups._reconcile_champions_dropouts(self.conn, self.edition_id)

        europa = self.conn.execute(
            """SELECT away_team,source_away,status
               FROM cup_matches
               WHERE edition_id=? AND competition='europa'
                 AND round_key='R16' AND match_index=0""",
            (self.edition_id,),
        ).fetchone()
        self.assertEqual(changed, 1)
        self.assertEqual(europa["away_team"], "Champions B0")
        self.assertEqual(europa["source_away"], "Perdedor Champions • Partido 1")
        self.assertEqual(europa["status"], "PENDING")

        # Idempotent: running the repair again must not duplicate/change anything.
        self.assertEqual(
            cups._reconcile_champions_dropouts(self.conn, self.edition_id),
            0,
        )

    def test_reconcile_does_not_rewrite_already_played_europa_match(self):
        self.conn.execute(
            """UPDATE cup_matches
               SET loser_team='Champions B0',winner_team='Champions A0',
                   status='FINISHED'
               WHERE edition_id=? AND competition='champions'
                 AND round_key='R16' AND match_index=0""",
            (self.edition_id,),
        )
        europa = self.conn.execute(
            """SELECT id FROM cup_matches
               WHERE edition_id=? AND competition='europa'
                 AND round_key='R16' AND match_index=0""",
            (self.edition_id,),
        ).fetchone()
        self.conn.execute(
            """UPDATE cup_matches
               SET home_team='Europa Seed',away_team='Old Drop',
                   winner_team='Europa Seed',loser_team='Old Drop',status='FINISHED'
               WHERE id=?""",
            (int(europa["id"]),),
        )

        changed = cups._reconcile_champions_dropouts(self.conn, self.edition_id)

        after = self.conn.execute(
            "SELECT away_team FROM cup_matches WHERE id=?",
            (int(europa["id"]),),
        ).fetchone()
        self.assertEqual(changed, 0)
        self.assertEqual(after["away_team"], "Old Drop")


if __name__ == "__main__":
    unittest.main()
