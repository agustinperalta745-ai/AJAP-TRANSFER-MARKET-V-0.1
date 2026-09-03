"""Repair the two Zaragoza/Bolton result cards misread as Middlesbrough.

The mobile Resultados gallery reads `league_ges_result_queue`, while standings
and audit flows read `league_matches` / evidence tables.  Keep every persisted
representation aligned for the two known pre-season results from 2026-09-02:

- Bolton Wanderers 0-2 Real Zaragoza
- Real Zaragoza 4-1 Bolton Wanderers

The repair is intentionally score-specific and date-bounded so later legitimate
Middlesbrough v Zaragoza fixtures are never rewritten.
"""

from __future__ import annotations

import json

import guild_isolation_patch as guild_isolation
import league_automation_patch as league


APP = None
BOT = None
_CUTOFF = "2026-09-04 00:00:00"


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
    )


def _columns(conn, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _historical_clause() -> str:
    return "(created_at IS NULL OR datetime(created_at) < datetime(?))"


def _candidate_sources(conn) -> set[int]:
    sources: set[int] = set()
    for table in ("league_ges_result_queue", "league_matches", "league_result_evidence"):
        cols = _columns(conn, table)
        needed = {"source_message_id", "home_team", "away_team", "home_goals", "away_goals"}
        if not needed.issubset(cols):
            continue
        created_filter = _historical_clause() if "created_at" in cols else "1=1"
        params = [_CUTOFF] if "created_at" in cols else []
        rows = conn.execute(
            f"""
            SELECT source_message_id, home_team, away_team, home_goals, away_goals
            FROM {table}
            WHERE {created_filter}
              AND (
                    (home_team='Middlesbrough' COLLATE NOCASE
                     AND away_team='Real Zaragoza' COLLATE NOCASE
                     AND home_goals=0 AND away_goals=2)
                 OR (home_team='Real Zaragoza' COLLATE NOCASE
                     AND away_team='Middlesbrough' COLLATE NOCASE
                     AND home_goals=4 AND away_goals=1)
              )
            """,
            tuple(params),
        ).fetchall()
        for row in rows:
            sources.add(int(row["source_message_id"]))
    return sources


def _fix_json(raw: str | None) -> str | None:
    if not raw:
        return raw
    try:
        payload = json.loads(raw)
    except Exception:
        return raw
    if not isinstance(payload, dict):
        return raw

    try:
        hg = int(payload.get("home_goals"))
        ag = int(payload.get("away_goals"))
    except (TypeError, ValueError):
        hg = ag = None

    home = str(payload.get("home_team") or "").strip()
    away = str(payload.get("away_team") or "").strip()
    changed = False
    if home.casefold() == "middlesbrough" and away.casefold() == "real zaragoza" and hg == 0 and ag == 2:
        payload["home_team"] = "Bolton Wanderers"
        changed = True
    elif home.casefold() == "real zaragoza" and away.casefold() == "middlesbrough" and hg == 4 and ag == 1:
        payload["away_team"] = "Bolton Wanderers"
        changed = True

    if not changed:
        # Source id already identifies one of the two known rows, so payloads that
        # only preserved the misread team name should still be made consistent.
        if home.casefold() == "middlesbrough":
            payload["home_team"] = "Bolton Wanderers"
            changed = True
        if away.casefold() == "middlesbrough":
            payload["away_team"] = "Bolton Wanderers"
            changed = True
    return json.dumps(payload, ensure_ascii=False) if changed else raw


def _repair(runtime, guild_id: int) -> tuple[bool, set[int]]:
    conn = league.db(runtime, int(guild_id))
    try:
        sources = _candidate_sources(conn)
        if not sources:
            return False, set()

        conn.execute("BEGIN IMMEDIATE")
        placeholders = ",".join("?" for _ in sources)
        source_params = tuple(sorted(sources))
        changed = False

        for table in ("league_ges_result_queue", "league_matches", "league_result_evidence", "league_manual_reviews"):
            cols = _columns(conn, table)
            if not {"source_message_id", "home_team", "away_team"}.issubset(cols):
                continue

            cur = conn.execute(
                f"""
                UPDATE {table}
                SET home_team=CASE WHEN home_team='Middlesbrough' COLLATE NOCASE
                                   THEN 'Bolton Wanderers' ELSE home_team END,
                    away_team=CASE WHEN away_team='Middlesbrough' COLLATE NOCASE
                                   THEN 'Bolton Wanderers' ELSE away_team END
                    {', updated_at=CURRENT_TIMESTAMP' if 'updated_at' in cols else ''}
                WHERE source_message_id IN ({placeholders})
                  AND (home_team='Middlesbrough' COLLATE NOCASE
                       OR away_team='Middlesbrough' COLLATE NOCASE)
                """,
                source_params,
            )
            changed = changed or cur.rowcount > 0

            if "payload_json" in cols:
                rows = conn.execute(
                    f"SELECT source_message_id, payload_json FROM {table} WHERE source_message_id IN ({placeholders})",
                    source_params,
                ).fetchall()
                for row in rows:
                    fixed = _fix_json(row["payload_json"])
                    if fixed != row["payload_json"]:
                        conn.execute(
                            f"UPDATE {table} SET payload_json=? WHERE source_message_id=?",
                            (fixed, int(row["source_message_id"])),
                        )
                        changed = True

        if _table_exists(conn, "league_goal_events"):
            cur = conn.execute(
                f"""
                UPDATE league_goal_events
                SET team='Bolton Wanderers'
                WHERE source_message_id IN ({placeholders})
                  AND team='Middlesbrough' COLLATE NOCASE
                """,
                source_params,
            )
            changed = changed or cur.rowcount > 0

        conn.commit()
        return changed, sources
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


async def _repair_guild(runtime, bot, guild_id: int):
    try:
        changed, sources = _repair(runtime, int(guild_id))
    except Exception as exc:
        print(f"AJAP Zaragoza/Bolton history repair guild={guild_id}: {type(exc).__name__}: {exc}")
        return
    if not changed:
        return
    print(
        "AJAP history repair: Zaragoza/Bolton corrected in Liga + GES gallery | "
        f"guild={guild_id} sources={','.join(str(x) for x in sorted(sources))}"
    )
    try:
        await league.refresh(runtime, bot, int(guild_id))
    except Exception as exc:
        print(f"AJAP Zaragoza/Bolton refresh guild={guild_id}: {exc}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_zaragoza_bolton_history_fix", False):
        return

    @bot.listen("on_ready")
    async def _ajap_zaragoza_bolton_history_repair():
        for guild in list(bot.guilds):
            await _repair_guild(runtime, bot, int(guild.id))

    runtime._ajap_zaragoza_bolton_history_fix = True
    print("AJAP historical fix ready: Zaragoza/Bolton 0-2 + 4-1")


_ORIGINAL = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_zaragoza_bolton_history_fix_wrapper", False):
    _apply._ajap_zaragoza_bolton_history_fix_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
