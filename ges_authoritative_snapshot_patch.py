"""Make every manual GES synchronization an authoritative current snapshot.

GES is the only source of truth for the active competition. A sync replaces the
active competition's matches, standings and scorers atomically instead of
merging them with rows left by previous imports/OCR/manual result flows.

Finished competition rows remain untouched so historical seasons and classics
can still be consulted after a competition is archived.
"""

from __future__ import annotations

import asyncio
import os

import competition_cycle as cycle
import league_ges_manual_sync_patch as ges


def _table(conn, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
    )


def _cols(conn, table: str) -> set[str]:
    if not _table(conn, table):
        return set()
    return {
        str(row["name"])
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def _fixture_key(home: str, away: str) -> tuple[str, str]:
    return ges._norm(home), ges._norm(away)


def _current_rows(conn, competition_id: int | None):
    if not _table(conn, "league_matches"):
        return []
    cols = _cols(conn, "league_matches")
    if competition_id is not None and "competition_id" in cols:
        return conn.execute(
            """SELECT source_message_id,home_team,away_team,home_goals,away_goals
               FROM league_matches WHERE competition_id=?""",
            (int(competition_id),),
        ).fetchall()
    # Legacy DB without competition scoping: there is no safe historical/current
    # distinction, so authoritative GES means replacing the live result set.
    return conn.execute(
        """SELECT source_message_id,home_team,away_team,home_goals,away_goals
           FROM league_matches"""
    ).fetchall()


def _delete_current_rows(conn, competition_id: int | None) -> None:
    if _table(conn, "league_matches"):
        cols = _cols(conn, "league_matches")
        if competition_id is not None and "competition_id" in cols:
            conn.execute(
                "DELETE FROM league_matches WHERE competition_id=?",
                (int(competition_id),),
            )
        else:
            conn.execute("DELETE FROM league_matches")

    # Goal events from the retired screenshot/OCR flow must never be mixed with
    # current GES scorers. Historical editions stay intact when they are scoped.
    if _table(conn, "league_goal_events"):
        cols = _cols(conn, "league_goal_events")
        if competition_id is not None and "competition_id" in cols:
            conn.execute(
                "DELETE FROM league_goal_events WHERE competition_id=?",
                (int(competition_id),),
            )
        else:
            conn.execute("DELETE FROM league_goal_events")

    # This queue belonged to the old Discord -> GES recognition/upload workflow,
    # which is no longer authoritative. Keeping its cards would make old results
    # reappear in Mobile even after a clean GES snapshot.
    if _table(conn, "league_ges_result_queue"):
        cols = _cols(conn, "league_ges_result_queue")
        raw_guild = str(os.getenv("AJPA_MOBILE_GUILD_ID") or os.getenv("DISCORD_GUILD_ID") or "").strip()
        if "guild_id" in cols and raw_guild.isdigit():
            conn.execute(
                "DELETE FROM league_ges_result_queue WHERE guild_id=?",
                (int(raw_guild),),
            )
        else:
            conn.execute("DELETE FROM league_ges_result_queue")


def _insert_match(conn, item: dict, staff_user_id: int | None, competition_id: int | None) -> int:
    source_id = ges._source_id(item["home_team"], item["away_team"])
    cols = _cols(conn, "league_matches")
    if "competition_id" in cols:
        conn.execute(
            """INSERT INTO league_matches
               (source_message_id,source_channel_id,author_id,home_team,away_team,
                home_goals,away_goals,confidence,competition_id)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                int(source_id),
                0,
                int(staff_user_id or 0),
                item["home_team"],
                item["away_team"],
                int(item["home_goals"]),
                int(item["away_goals"]),
                1.0,
                int(competition_id) if competition_id is not None else None,
            ),
        )
    else:
        conn.execute(
            """INSERT INTO league_matches
               (source_message_id,source_channel_id,author_id,home_team,away_team,
                home_goals,away_goals,confidence)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                int(source_id),
                0,
                int(staff_user_id or 0),
                item["home_team"],
                item["away_team"],
                int(item["home_goals"]),
                int(item["away_goals"]),
                1.0,
            ),
        )
    return int(source_id)


async def _authoritative_sync(runtime, bot, guild_id: int, staff_user_id: int | None = None) -> dict:
    if not ges._SYNC_LOCK.acquire(blocking=False):
        raise RuntimeError("Ya hay una sincronización GES en curso.")

    try:
        # Parse the complete remote snapshot before touching SQLite. If GES is
        # unreachable or its markup cannot be recognized, the previous good
        # snapshot remains intact.
        classification_html, scorers_html = await asyncio.gather(
            asyncio.to_thread(ges._fetch, ges.GES_CLASSIFICATION_URL),
            asyncio.to_thread(ges._fetch, ges.GES_SCORERS_URL),
        )
        classification_tables = ges._tables(classification_html)
        scorer_tables = ges._tables(scorers_html)
        standings, warnings_a = ges._parse_standings(classification_tables)
        matches, warnings_b = ges._parse_matches(classification_tables)
        scorers, warnings_c = ges._parse_scorers(scorer_tables)
        warnings = list(dict.fromkeys(warnings_a + warnings_b + warnings_c))

        # Never atomically replace a good current competition with a partially
        # recognized standings table. Unknown standings teams need an alias fix.
        unmapped_standings = [
            warning for warning in warnings_a
            if str(warning).startswith("Equipo de tabla sin vincular:")
        ]
        if unmapped_standings:
            raise RuntimeError(
                "GES contiene equipos que AJPA todavía no pudo vincular: "
                + "; ".join(unmapped_standings[:5])
            )

        conn = ges.league.db(runtime, int(guild_id))
        changed_sources: list[int] = []
        matches_new = 0
        matches_updated = 0
        matches_removed = 0
        try:
            ges._ensure_schema(conn)
            cycle.ensure_schema(conn)
            conn.commit()
            competition_id = cycle.active_competition_id(conn)
            conn.commit()

            old_rows = _current_rows(conn, competition_id)
            old_by_fixture = {
                _fixture_key(row["home_team"], row["away_team"]): row
                for row in old_rows
            }
            old_source_ids = {
                int(row["source_message_id"])
                for row in old_rows
                if row["source_message_id"] is not None
            }
            incoming_keys = {
                _fixture_key(item["home_team"], item["away_team"])
                for item in matches
            }

            for item in matches:
                key = _fixture_key(item["home_team"], item["away_team"])
                previous = old_by_fixture.get(key)
                if previous is None:
                    matches_new += 1
                elif (
                    int(previous["home_goals"]) != int(item["home_goals"])
                    or int(previous["away_goals"]) != int(item["away_goals"])
                ):
                    matches_updated += 1
            matches_removed = sum(
                1 for key in old_by_fixture if key not in incoming_keys
            )

            conn.execute("BEGIN IMMEDIATE")

            # Snapshot tables: delete first, then insert exactly what GES says now.
            conn.execute(
                "DELETE FROM league_ges_standings WHERE guild_id=? AND league_id=?",
                (int(guild_id), ges.GES_LEAGUE_ID),
            )
            for row in standings:
                conn.execute(
                    """INSERT INTO league_ges_standings
                       (guild_id,league_id,position,team,pts,pj,pg,pe,pp,gf,gc,dg)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        int(guild_id), ges.GES_LEAGUE_ID, int(row["position"]),
                        row["team"], int(row["pts"]), int(row["pj"]),
                        int(row["pg"]), int(row["pe"]), int(row["pp"]),
                        int(row["gf"]), int(row["gc"]), int(row["dg"]),
                    ),
                )

            _delete_current_rows(conn, competition_id)
            new_source_ids: set[int] = set()
            for item in matches:
                new_source_ids.add(
                    _insert_match(conn, item, staff_user_id, competition_id)
                )

            conn.execute(
                "DELETE FROM league_ges_scorers WHERE guild_id=? AND league_id=?",
                (int(guild_id), ges.GES_LEAGUE_ID),
            )
            for row in scorers:
                conn.execute(
                    """INSERT INTO league_ges_scorers
                       (guild_id,league_id,player,team,goals)
                       VALUES(?,?,?,?,?)""",
                    (
                        int(guild_id), ges.GES_LEAGUE_ID, row["player"],
                        row["team"] or "", int(row["goals"]),
                    ),
                )

            conn.execute(
                """INSERT INTO league_ges_sync_runs
                   (guild_id,league_id,staff_user_id,standings_count,matches_new,
                    matches_updated,scorers_count,warning_count)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    int(guild_id), ges.GES_LEAGUE_ID, staff_user_id,
                    len(standings), matches_new, matches_updated,
                    len(scorers), len(warnings),
                ),
            )
            conn.commit()
            changed_sources = sorted(old_source_ids | new_source_ids)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        warnings.extend(
            await ges._refresh_downstream(
                runtime, bot, int(guild_id), changed_sources
            )
        )
        warnings = list(dict.fromkeys(warnings))
        return {
            "ok": True,
            "league_id": ges.GES_LEAGUE_ID,
            "source_of_truth": "GES",
            "snapshot_replaced": True,
            "standings": len(standings),
            "matches_read": len(matches),
            "matches_new": matches_new,
            "matches_updated": matches_updated,
            "matches_removed": matches_removed,
            "scorers": len(scorers),
            "warnings": warnings[:40],
        }
    finally:
        ges._SYNC_LOCK.release()


def _install_mobile_snapshot_reader() -> None:
    """Make /api/v1/league show GES points/scorers verbatim when available."""
    import mobile_league_history_api_patch as history
    import mobile_parity_api_patch as parity

    # Ensure the final history wrapper exists first. We then wrap that final
    # payload so it can keep archived match history while GES owns live tables.
    parity.apply_mobile_parity_api_patch()
    history.apply_mobile_league_history_api_patch()

    current = parity.league_payload
    if getattr(current, "_ajpa_ges_authoritative_snapshot", False):
        return

    def authoritative_payload(conn):
        payload = dict(current(conn))
        if not _table(conn, "league_ges_standings"):
            return payload

        raw_guild = str(
            os.getenv("AJPA_MOBILE_GUILD_ID")
            or os.getenv("DISCORD_GUILD_ID")
            or ""
        ).strip()
        params: tuple = (ges.GES_LEAGUE_ID,)
        guild_clause = ""
        if raw_guild.isdigit() and "guild_id" in _cols(conn, "league_ges_standings"):
            guild_clause = " AND guild_id=?"
            params = (ges.GES_LEAGUE_ID, int(raw_guild))

        rows = conn.execute(
            """SELECT position,team,pts,pj,pg,pe,pp,gf,gc,dg
               FROM league_ges_standings
               WHERE league_id=?"""
            + guild_clause
            + " ORDER BY position ASC, team COLLATE NOCASE ASC",
            params,
        ).fetchall()
        if not rows:
            return payload

        payload["standings"] = [
            {
                "position": int(row["position"]),
                "team": str(row["team"]),
                "pts": int(row["pts"]),
                "pj": int(row["pj"]),
                "pg": int(row["pg"]),
                "pe": int(row["pe"]),
                "pp": int(row["pp"]),
                "gf": int(row["gf"]),
                "gc": int(row["gc"]),
                "dg": int(row["dg"]),
            }
            for row in rows
        ]

        if _table(conn, "league_ges_scorers"):
            scorer_params: tuple = (ges.GES_LEAGUE_ID,)
            scorer_guild_clause = ""
            if raw_guild.isdigit() and "guild_id" in _cols(conn, "league_ges_scorers"):
                scorer_guild_clause = " AND guild_id=?"
                scorer_params = (ges.GES_LEAGUE_ID, int(raw_guild))
            scorer_rows = conn.execute(
                """SELECT player,team,goals FROM league_ges_scorers
                   WHERE league_id=?"""
                + scorer_guild_clause
                + " ORDER BY goals DESC, player COLLATE NOCASE ASC",
                scorer_params,
            ).fetchall()
            payload["scorers"] = [
                {
                    "player": str(row["player"]),
                    "team": str(row["team"] or ""),
                    "goals": int(row["goals"]),
                }
                for row in scorer_rows
            ]

        payload["source_of_truth"] = "GES"
        payload["ges_authoritative"] = True
        return payload

    authoritative_payload._ajpa_ges_authoritative_snapshot = True
    authoritative_payload._ajpa_ges_authoritative_snapshot_base = current
    parity.league_payload = authoritative_payload


def apply_authoritative_ges_snapshot(runtime, bot) -> None:
    if getattr(runtime, "_ajpa_ges_authoritative_snapshot", False):
        return

    # Make sure the base Staff endpoint exists, then replace its module-global
    # sync function. The endpoint resolves that global at request time.
    ges.apply_manual_ges_sync(runtime, bot)
    ges.sync_from_ges = _authoritative_sync
    _install_mobile_snapshot_reader()

    runtime._ajpa_ges_authoritative_snapshot = True
    print(
        "AJPA GES authoritative snapshot activo: current competition replace + "
        "Mobile standings/scorers read directly from GES"
    )
