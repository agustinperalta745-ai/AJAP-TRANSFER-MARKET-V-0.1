"""Limita la reparación Everton/Villarreal al partido existente previo al arreglo."""

import league_automation_patch as league
import league_text_scorer_repair_patch as scorer_patch


_CUTOFF = "2026-09-02 00:00:00"


def _repair_existing_everton_villarreal_only(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    inserted = 0
    try:
        matches = conn.execute(
            """
            SELECT * FROM league_matches
            WHERE ((home_team='Everton' AND away_team='Villarreal')
                OR (home_team='Villarreal' AND away_team='Everton'))
              AND home_goals=1 AND away_goals=1
              AND created_at < ?
            """,
            (_CUTOFF,),
        ).fetchall()

        for match in matches:
            source_id = int(match["source_message_id"])
            rows = conn.execute(
                """
                SELECT team, SUM(goals) AS goals
                FROM league_goal_events
                WHERE source_message_id=?
                GROUP BY team COLLATE NOCASE
                """,
                (source_id,),
            ).fetchall()
            totals = {
                league.canonical_team(row["team"]): int(row["goals"] or 0)
                for row in rows
                if league.canonical_team(row["team"])
            }

            missing = []
            if totals.get("Everton", 0) == 0:
                player = scorer_patch._resolve_written_player(
                    runtime, guild_id, "Van der Meyde", "Everton"
                )
                if player:
                    missing.append((player, "Everton"))
            if totals.get("Villarreal", 0) == 0:
                player = scorer_patch._resolve_written_player(
                    runtime, guild_id, "Juan Román Riquelme", "Villarreal"
                )
                if player:
                    missing.append((player, "Villarreal"))
            if not missing:
                continue

            conn.execute("BEGIN IMMEDIATE")
            for player, team in missing:
                exists = conn.execute(
                    """
                    SELECT 1 FROM league_goal_events
                    WHERE source_message_id=? AND player=? COLLATE NOCASE
                    LIMIT 1
                    """,
                    (source_id, player),
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    """
                    INSERT INTO league_goal_events
                        (source_message_id, player, team, goals, confidence)
                    VALUES (?, ?, ?, 1, 1.0)
                    """,
                    (source_id, player, team),
                )
                inserted += 1
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
    return inserted


# El listener ya registrado por scorer_patch resuelve este global cuando corre.
scorer_patch._repair_everton_villarreal = _repair_existing_everton_villarreal_only
