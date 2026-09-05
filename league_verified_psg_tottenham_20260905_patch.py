"""One-time verified correction for PSG 1-2 Tottenham on 2026-09-05.

User-provided PES6 screenshots prove:
- Paris Saint-Germain 1-2 Tottenham
- Pauleta x1 (PSG)
- Robbie Keane x1 (Tottenham)
- Davids x1 (Tottenham)

The bot had stored the affected result as 1-1. This repair is deliberately
bounded to exactly one PSG-home/Tottenham-away 1-1 match created on 2026-09-05.
It edits the existing official row, rewrites scorer attribution from the verified
screen, synchronizes GES/manual-review rows, and refreshes Liga/app/Discord.
"""
from __future__ import annotations

import unicodedata

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_persistent_result_correction_patch as corrections
import league_persistent_result_admin_controls_patch as admin_controls
import league_result_message_sync_patch as public_sync


FIX_KEY = "verified_psg_tottenham_1_2_20260905_v1"
MATCH_DATE = "2026-09-05"
APP = None
BOT = None


def _norm(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().replace("–", "-").split())


def _is_psg(value) -> bool:
    text = _norm(league.canonical_team(value) or value)
    return "saint-germain" in text or text in {"psg", "paris saint germain"}


def _is_tottenham(value) -> bool:
    text = _norm(league.canonical_team(value) or value)
    return "tottenham" in text


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _ensure_fix_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ajap_runtime_fixes (
            fix_key TEXT PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _candidate(conn):
    rows = conn.execute(
        """
        SELECT *
        FROM league_matches
        WHERE home_goals=1
          AND away_goals=1
          AND substr(COALESCE(created_at,''),1,10)=?
        ORDER BY id DESC
        """,
        (MATCH_DATE,),
    ).fetchall()
    matches = [
        row for row in rows
        if _is_psg(row["home_team"]) and _is_tottenham(row["away_team"])
    ]
    return matches[0] if len(matches) == 1 else None


def _apply_verified_fix(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_fix_table(conn)
        conn.commit()
        if conn.execute(
            "SELECT 1 FROM ajap_runtime_fixes WHERE fix_key=? LIMIT 1",
            (FIX_KEY,),
        ).fetchone():
            return None

        match = _candidate(conn)
        if match is None:
            return None

        source_id = int(match["source_message_id"])
        home = str(match["home_team"])
        away = str(match["away_team"])
        old_hg = int(match["home_goals"])
        old_ag = int(match["away_goals"])

        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
            (source_id,),
        ).fetchone()
        if (
            current is None
            or int(current["home_goals"]) != 1
            or int(current["away_goals"]) != 1
            or not _is_psg(current["home_team"])
            or not _is_tottenham(current["away_team"])
        ):
            conn.rollback()
            return None

        home = str(current["home_team"])
        away = str(current["away_team"])
        conn.execute(
            """
            UPDATE league_matches
            SET home_goals=1, away_goals=2, confidence=1.0
            WHERE source_message_id=?
            """,
            (source_id,),
        )

        corrections._sync_related_rows(conn, source_id, home, away, 1, 2, 0)

        # The screenshot is authoritative, so replace any OCR-derived scorer rows
        # for this source instead of incrementing totals and risking duplicates.
        conn.execute(
            "DELETE FROM league_goal_events WHERE source_message_id=?",
            (source_id,),
        )
        for player, team in (
            ("Pauleta", home),
            ("Robbie Keane", away),
            ("Davids", away),
        ):
            conn.execute(
                """
                INSERT INTO league_goal_events
                    (source_message_id, player, team, goals, confidence)
                VALUES (?, ?, ?, 1, 1.0)
                """,
                (source_id, player, team),
            )

        # Keep an explicit audit trail identical to normal Staff corrections.
        conn.execute(
            """
            INSERT INTO league_result_corrections(
                source_message_id, corrected_by,
                old_home_team, old_away_team, old_home_goals, old_away_goals,
                new_home_team, new_away_team, new_home_goals, new_away_goals
            ) VALUES (?,0,?,?,?,?,?,?,?,?)
            """,
            (
                source_id,
                home, away, old_hg, old_ag,
                home, away, 1, 2,
            ),
        )
        league.standings(conn)
        conn.execute(
            "INSERT OR REPLACE INTO ajap_runtime_fixes(fix_key, applied_at) VALUES (?, CURRENT_TIMESTAMP)",
            (FIX_KEY,),
        )
        conn.commit()
        return source_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _apply_on_ready():
    if APP is None or BOT is None:
        return
    for guild in list(BOT.guilds):
        try:
            source_id = _apply_verified_fix(APP, guild.id)
            if not source_id:
                continue

            # Refresh standings/app plus active GES cards using the same path as
            # a normal Staff correction.
            try:
                await admin_controls._refresh_everything(APP, BOT, guild.id)
            except Exception as exc:
                print(
                    "WARNING AJAP PSG-Tottenham refresh: "
                    f"{type(exc).__name__}: {exc}"
                )

            try:
                public_sync.APP = APP
                public_sync.BOT = BOT
                await public_sync.sync_public_reply(
                    guild, source_id, corrected=True, force=True
                )
            except Exception as exc:
                print(
                    "WARNING AJAP PSG-Tottenham public sync: "
                    f"{type(exc).__name__}: {exc}"
                )

            print(
                "AJAP verified correction applied: "
                f"guild={guild.id} source={source_id} | PSG 1-2 Tottenham | "
                "Pauleta x1, Robbie Keane x1, Davids x1"
            )
        except Exception as exc:
            print(
                "WARNING AJAP PSG-Tottenham correction "
                f"guild={getattr(guild, 'id', '?')}: {type(exc).__name__}: {exc}"
            )


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(bot, "_ajap_verified_psg_tottenham_listener", False):
        return
    bot.add_listener(_apply_on_ready, "on_ready")
    bot._ajap_verified_psg_tottenham_listener = True
    print("AJAP verified correction armed: PSG 1-2 Tottenham (2026-09-05)")


_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_verified_psg_tottenham_wrapper",
    False,
):
    _apply._ajap_verified_psg_tottenham_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
