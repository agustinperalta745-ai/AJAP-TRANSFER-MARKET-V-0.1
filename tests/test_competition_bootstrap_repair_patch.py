import sqlite3
import unittest

import competition_bootstrap_repair_patch as repair
import competition_cycle as cycle


class CompetitionBootstrapRepairTests(unittest.TestCase):
    def connection(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                active INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO seasons(name,active) VALUES('Temporada 1',1);

            CREATE TABLE league_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_message_id INTEGER,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                home_goals INTEGER NOT NULL,
                away_goals INTEGER NOT NULL,
                created_at DATETIME
            );
            INSERT INTO league_matches(
                source_message_id,home_team,away_team,home_goals,away_goals,created_at
            ) VALUES(1001,'Lyon','Marsella',3,2,'2026-09-01 18:00:00');

            CREATE TABLE league_goal_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player TEXT NOT NULL,
                team TEXT,
                goals INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME
            );
            INSERT INTO league_goal_events(player,team,goals,created_at)
            VALUES('Jugador A','Lyon',2,'2026-09-01 18:00:00');
            """
        )
        conn.commit()
        return conn

    def test_moves_legacy_rows_into_started_season_one_without_deleting(self):
        conn = self.connection()
        try:
            cycle.ensure_schema(conn)
            preseason = conn.execute(
                "SELECT competition_id FROM competition_cycle_state WHERE id=1"
            ).fetchone()
            preseason_id = int(preseason["competition_id"])
            self.assertEqual(
                conn.execute(
                    "SELECT competition_id FROM league_matches WHERE id=1"
                ).fetchone()["competition_id"],
                preseason_id,
            )

            cycle.advance(conn, 99, cycle.PRESEASON)
            state = conn.execute(
                "SELECT phase,competition_id FROM competition_cycle_state WHERE id=1"
            ).fetchone()
            self.assertEqual(state["phase"], cycle.SEASON)
            season_id = int(state["competition_id"])
            self.assertNotEqual(season_id, preseason_id)
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) c FROM league_matches WHERE competition_id=?",
                    (season_id,),
                ).fetchone()["c"],
                0,
            )

            before_matches = conn.execute(
                "SELECT COUNT(*) c FROM league_matches"
            ).fetchone()["c"]
            before_goals = conn.execute(
                "SELECT COUNT(*) c FROM league_goal_events"
            ).fetchone()["c"]

            result = repair.repair_conn(conn)
            conn.commit()

            self.assertTrue(result["changed"])
            self.assertEqual(result["moved_matches"], 1)
            self.assertEqual(result["moved_goals"], 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM league_matches").fetchone()["c"],
                before_matches,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM league_goal_events").fetchone()["c"],
                before_goals,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT competition_id FROM league_matches WHERE id=1"
                ).fetchone()["competition_id"],
                season_id,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT competition_id FROM league_goal_events WHERE id=1"
                ).fetchone()["competition_id"],
                season_id,
            )

            again = repair.repair_conn(conn)
            self.assertFalse(again["changed"])
            self.assertEqual(again["reason"], "already_applied")
        finally:
            conn.close()

    def test_converts_bootstrap_to_running_season_if_staff_never_advanced(self):
        conn = self.connection()
        try:
            cycle.ensure_schema(conn)
            state_before = conn.execute(
                "SELECT phase,competition_id FROM competition_cycle_state WHERE id=1"
            ).fetchone()
            bootstrap_id = int(state_before["competition_id"])
            self.assertEqual(state_before["phase"], cycle.PRESEASON)

            result = repair.repair_conn(conn)
            conn.commit()

            self.assertTrue(result["changed"])
            self.assertTrue(result["converted_bootstrap"])
            state_after = conn.execute(
                "SELECT phase,competition_id FROM competition_cycle_state WHERE id=1"
            ).fetchone()
            self.assertEqual(state_after["phase"], cycle.SEASON)
            self.assertEqual(int(state_after["competition_id"]), bootstrap_id)
            edition = conn.execute(
                "SELECT kind,label FROM competition_editions WHERE id=?",
                (bootstrap_id,),
            ).fetchone()
            self.assertEqual(edition["kind"], "season")
            self.assertEqual(edition["label"], "Temporada 1")
            self.assertEqual(
                conn.execute(
                    "SELECT competition_id FROM league_matches WHERE id=1"
                ).fetchone()["competition_id"],
                bootstrap_id,
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
