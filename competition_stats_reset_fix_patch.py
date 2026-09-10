"""Keep live standings/scorers strictly scoped to the active AJPA competition.

The authoritative GES cache is only a LIVE snapshot. Historical results live in
league_matches/league_goal_events plus competition_editions.final_snapshot_json.
When AJPA advances to a new playable competition, stale GES cache rows must not
bleed into the new table or scorer ranking.
"""

from __future__ import annotations

import os
import sqlite3

import competition_cycle as cycle
import ges_authoritative_snapshot_patch as authoritative
import league_ges_manual_sync_patch as ges
import mobile_parity_api_patch as parity


_BASE_ADVANCE = cycle.advance
_BASE_AUTHORITATIVE_APPLY = authoritative.apply_authoritative_ges_snapshot


def _table(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
    )


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table(conn, table):
        return set()
    return {
        str(row["name"])
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def _clear_live_ges_cache(conn: sqlite3.Connection) -> None:
    """Clear only disposable live GES snapshots, never historical matches."""
    if _table(conn, "league_ges_standings"):
        conn.execute("DELETE FROM league_ges_standings")
    if _table(conn, "league_ges_scorers"):
        conn.execute("DELETE FROM league_ges_scorers")


def _advance_with_clean_live_stats(conn, user_id, expected_phase=None):
    cycle.ensure_schema(conn)
    before = conn.execute(
        "SELECT phase,competition_id FROM competition_cycle_state WHERE id=1"
    ).fetchone()
    old_cid = (
        int(before["competition_id"])
        if before is not None and before["competition_id"] is not None
        else None
    )

    result = _BASE_ADVANCE(conn, user_id, expected_phase)
    new_cid = result.get("competition_id")
    new_cid = int(new_cid) if new_cid is not None else None

    # A new competition gets a completely clean LIVE table/scorer cache. The
    # finished competition was already archived by competition_cycle._finish().
    if new_cid is not None and new_cid != old_cid:
        _clear_live_ges_cache(conn)
        conn.commit()
    return result


cycle.advance = _advance_with_clean_live_stats


def _active_ges_context(conn: sqlite3.Connection):
    if not _table(conn, "competition_cycle_state"):
        return None
    state = conn.execute(
        "SELECT phase,competition_id FROM competition_cycle_state WHERE id=1"
    ).fetchone()
    if (
        state is None
        or str(state["phase"] or "") not in cycle.PLAYABLE
        or state["competition_id"] is None
    ):
        return None

    cid = int(state["competition_id"])
    started_at = None
    if _table(conn, "competition_editions"):
        edition = conn.execute(
            "SELECT started_at FROM competition_editions WHERE id=?",
            (cid,),
        ).fetchone()
        started_at = str(edition["started_at"] or "") if edition else ""

    if not _table(conn, "league_ges_competition_config"):
        return {"competition_id": cid, "started_at": started_at or "", "league_id": None}
    cfg = conn.execute(
        "SELECT league_id FROM league_ges_competition_config WHERE competition_id=?",
        (cid,),
    ).fetchone()
    return {
        "competition_id": cid,
        "started_at": started_at or "",
        "league_id": str(cfg["league_id"]) if cfg and cfg["league_id"] is not None else None,
    }


def _guild_filter(conn: sqlite3.Connection, table: str):
    raw = str(
        os.getenv("AJPA_MOBILE_GUILD_ID")
        or os.getenv("DISCORD_GUILD_ID")
        or ""
    ).strip()
    if raw.isdigit() and "guild_id" in _cols(conn, table):
        return " AND guild_id=?", [int(raw)]
    return "", []


def _cache_is_current(
    conn: sqlite3.Connection,
    table: str,
    league_id: str,
    started_at: str,
) -> bool:
    if not _table(conn, table):
        return False
    guild_clause, guild_params = _guild_filter(conn, table)
    row = conn.execute(
        f"SELECT MAX(updated_at) AS updated_at FROM {table} WHERE league_id=?{guild_clause}",
        (league_id, *guild_params),
    ).fetchone()
    latest = str(row["updated_at"] or "") if row else ""
    if not latest:
        return False
    if not started_at:
        return True
    check = conn.execute(
        "SELECT CASE WHEN datetime(?) >= datetime(?) THEN 1 ELSE 0 END AS ok",
        (latest, started_at),
    ).fetchone()
    return bool(check and int(check["ok"] or 0))


def _install_competition_safe_mobile_reader() -> None:
    current = parity.league_payload
    if getattr(current, "_ajpa_competition_safe_ges", False):
        return

    # The authoritative GES wrapper keeps a pointer to the competition-aware
    # payload it replaced. Start from that clean payload and only overlay GES
    # when the cache demonstrably belongs to the CURRENT competition.
    base = getattr(current, "_ajpa_ges_authoritative_snapshot_base", current)

    def safe_payload(conn: sqlite3.Connection) -> dict:
        payload = dict(base(conn))
        context = _active_ges_context(conn)
        if not context or not context.get("league_id"):
            return payload

        league_id = str(context["league_id"])
        started_at = str(context.get("started_at") or "")

        if _cache_is_current(conn, "league_ges_standings", league_id, started_at):
            guild_clause, guild_params = _guild_filter(conn, "league_ges_standings")
            rows = conn.execute(
                """SELECT position,team,pts,pj,pg,pe,pp,gf,gc,dg
                   FROM league_ges_standings WHERE league_id=?"""
                + guild_clause
                + " ORDER BY position ASC, team COLLATE NOCASE ASC",
                (league_id, *guild_params),
            ).fetchall()
            if rows:
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

        if _cache_is_current(conn, "league_ges_scorers", league_id, started_at):
            guild_clause, guild_params = _guild_filter(conn, "league_ges_scorers")
            rows = conn.execute(
                """SELECT player,team,goals FROM league_ges_scorers
                   WHERE league_id=?"""
                + guild_clause
                + " ORDER BY goals DESC, player COLLATE NOCASE ASC",
                (league_id, *guild_params),
            ).fetchall()
            payload["scorers"] = [
                {
                    "player": str(row["player"]),
                    "team": str(row["team"] or ""),
                    "goals": int(row["goals"]),
                }
                for row in rows
            ]

        payload["source_of_truth"] = "GES"
        payload["ges_authoritative"] = True
        payload["competition_id"] = int(context["competition_id"])
        return payload

    safe_payload._ajpa_competition_safe_ges = True
    safe_payload._ajpa_competition_safe_ges_base = base
    parity.league_payload = safe_payload
    print("AJPA Mobile: GES live table/scorers isolated by active competition")


def _repair_stale_cache(runtime) -> None:
    """Repair the already-started competition that exposed the bug in production."""
    conn = runtime.db()
    try:
        cycle.ensure_schema(conn)
        context = _active_ges_context(conn)
        if not context:
            return

        league_id = context.get("league_id")
        started_at = str(context.get("started_at") or "")
        changed = False

        for table in ("league_ges_standings", "league_ges_scorers"):
            if not _table(conn, table):
                continue
            # No GES config for the new competition means every cached row is
            # necessarily from an older edition.
            if not league_id:
                cur = conn.execute(f"DELETE FROM {table}")
                changed = changed or cur.rowcount != 0
                continue

            guild_clause, guild_params = _guild_filter(conn, table)
            if started_at:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE (league_id<>? OR datetime(updated_at)<datetime(?)){guild_clause}",
                    (str(league_id), started_at, *guild_params),
                )
            else:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE league_id<>?{guild_clause}",
                    (str(league_id), *guild_params),
                )
            changed = changed or cur.rowcount != 0

        if changed:
            conn.commit()
            print(
                "AJPA competencia activa: caché GES vieja eliminada; tabla y goleadores parten en cero"
            )
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(
            "WARNING AJPA reset competencia: no se pudo limpiar caché GES: "
            f"{type(exc).__name__}: {exc}"
        )
    finally:
        conn.close()


def _apply_authoritative_with_competition_guard(runtime, bot):
    _BASE_AUTHORITATIVE_APPLY(runtime, bot)
    _install_competition_safe_mobile_reader()
    _repair_stale_cache(runtime)


authoritative.apply_authoritative_ges_snapshot = _apply_authoritative_with_competition_guard
print("AJPA ciclo: reset real de tabla/goleadores entre competencias instalado")
