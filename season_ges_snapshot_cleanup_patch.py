"""Remove active-season results that disappeared from GES after a successful sync.

The season-aware synchronizer validates and imports all three configured pages.
This wrapper pre-validates the configured results page, lets that sync finish,
and only then removes active-edition fixtures no longer present in GES. Finished
competitions are never touched.
"""

from __future__ import annotations

import asyncio

import competition_cycle as cycle
import league_ges_manual_sync_patch as ges
import season_ges_authority_patch as seasonal


def _fixture_key(home: str, away: str) -> tuple[str, str]:
    return ges._norm(home), ges._norm(away)


def apply_season_snapshot_cleanup(runtime, bot) -> None:
    base_sync = ges.sync_from_ges
    if getattr(base_sync, "_ajpa_season_snapshot_cleanup", False):
        return

    async def sync_with_cleanup(
        runtime_arg,
        bot_arg,
        guild_id: int,
        staff_user_id: int | None = None,
    ) -> dict:
        conn = ges.league.db(runtime_arg, int(guild_id))
        try:
            cfg = seasonal._current_config_payload(conn)
            competition_id = int(cfg["competition_id"])
            if not cfg.get("configured"):
                return await base_sync(
                    runtime_arg, bot_arg, int(guild_id), staff_user_id
                )
            results_url = str(cfg["results_url"])
        finally:
            conn.close()

        # Validate the complete result snapshot before the base sync changes DB.
        results_html = await asyncio.to_thread(ges._fetch, results_url)
        parsed_matches, parse_warnings = ges._parse_matches(ges._tables(results_html))
        incoming_keys = {
            _fixture_key(item["home_team"], item["away_team"])
            for item in parsed_matches
        }

        result = await base_sync(
            runtime_arg, bot_arg, int(guild_id), staff_user_id
        )

        removed_sources: list[int] = []
        conn = ges.league.db(runtime_arg, int(guild_id))
        try:
            cycle.ensure_schema(conn)
            active_id = cycle.active_competition_id(conn)
            conn.commit()
            if active_id != competition_id:
                return result

            rows = conn.execute(
                """SELECT id,source_message_id,home_team,away_team
                   FROM league_matches WHERE competition_id=?""",
                (competition_id,),
            ).fetchall()
            stale = [
                row for row in rows
                if _fixture_key(row["home_team"], row["away_team"]) not in incoming_keys
            ]
            if stale:
                conn.execute("BEGIN IMMEDIATE")
                for row in stale:
                    conn.execute("DELETE FROM league_matches WHERE id=?", (int(row["id"]),))
                    if row["source_message_id"] is not None:
                        removed_sources.append(int(row["source_message_id"]))
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        merged = dict(result)
        merged["snapshot_replaced"] = True
        merged["source_of_truth"] = "GES"
        merged["matches_removed"] = len(removed_sources)
        if parse_warnings:
            warnings = list(merged.get("warnings") or [])
            warnings.extend(parse_warnings)
            merged["warnings"] = list(dict.fromkeys(warnings))[:40]

        if removed_sources:
            refresh_warnings = await ges._refresh_downstream(
                runtime_arg, bot_arg, int(guild_id), []
            )
            if refresh_warnings:
                warnings = list(merged.get("warnings") or [])
                warnings.extend(refresh_warnings)
                merged["warnings"] = list(dict.fromkeys(warnings))[:40]
        return merged

    sync_with_cleanup._ajpa_season_snapshot_cleanup = True
    sync_with_cleanup._ajpa_season_snapshot_cleanup_base = base_sync
    ges.sync_from_ges = sync_with_cleanup
    print("AJPA GES: competencia activa refleja el snapshot completo de resultados")
