"""One-time cleanup for the historical Real Betis test result.

The legacy AJAP guild still contains a test match that gave Real Betis 3 points:
Real Betis 2-0 Sevilla. Both the Discord Liga panel and the mobile app calculate
standings directly from league_matches, so the correct fix is to remove that test
match and its dependent Liga/GES records instead of applying a fake -3 adjustment.

The cleanup is intentionally restricted to the legacy guild and to the exact
2-0 Betis/Sevilla test score. It is idempotent and runs once after Discord is ready.
"""

from __future__ import annotations

import sqlite3

import guild_isolation_patch as guild_isolation
import league_automation_patch as league


APP = None
BOT = None


def _canon(value):
    return league.canonical_team(value) or str(value or "").strip()


def _target(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM league_matches
            WHERE datetime(created_at) < datetime('2026-09-02 00:00:00')
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        home = _canon(row["home_team"])
        away = _canon(row["away_team"])
        hg = int(row["home_goals"])
        ag = int(row["away_goals"])
        if home == "Real Betis" and away == "Sevilla" and hg == 2 and ag == 0:
            return row
        if home == "Sevilla" and away == "Real Betis" and hg == 0 and ag == 2:
            return row
    return None


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
    )


def _cleanup(runtime, guild_id: int):
    match = _target(runtime, int(guild_id))
    if not match:
        return None

    source_id = int(match["source_message_id"])
    ges_message = None
    ges_channel = None

    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute("BEGIN IMMEDIATE")

        if _table_exists(conn, "league_ges_result_queue"):
            row = conn.execute(
                "SELECT ges_channel_id, ges_message_id FROM league_ges_result_queue WHERE source_message_id=? LIMIT 1",
                (source_id,),
            ).fetchone()
            if row:
                ges_channel = int(row["ges_channel_id"]) if row["ges_channel_id"] else None
                ges_message = int(row["ges_message_id"]) if row["ges_message_id"] else None
            conn.execute(
                "DELETE FROM league_ges_result_queue WHERE source_message_id=?",
                (source_id,),
            )

        for table in (
            "league_goal_events",
            "league_image_hashes",
            "league_result_evidence",
            "league_manual_reviews",
        ):
            if not _table_exists(conn, table):
                continue
            if table == "league_image_hashes":
                conn.execute(
                    "DELETE FROM league_image_hashes WHERE source_message_id=?",
                    (source_id,),
                )
            else:
                conn.execute(
                    f"DELETE FROM {table} WHERE source_message_id=?",
                    (source_id,),
                )

        conn.execute("DELETE FROM league_matches WHERE source_message_id=?", (source_id,))
        conn.commit()
        print(
            "AJAP Liga cleanup: eliminado resultado de prueba Real Betis 2-0 Sevilla "
            f"source={source_id}"
        )
        return {
            "source_message_id": source_id,
            "source_channel_id": int(match["source_channel_id"]),
            "ges_channel_id": ges_channel,
            "ges_message_id": ges_message,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _cleanup_discord_artifacts(bot, guild, result):
    if not result:
        return

    # Remove the stale GES test card if it still exists.
    if result.get("ges_channel_id") and result.get("ges_message_id"):
        try:
            channel = guild.get_channel(int(result["ges_channel_id"]))
            if channel is None:
                channel = await guild.fetch_channel(int(result["ges_channel_id"]))
            message = await channel.fetch_message(int(result["ges_message_id"]))
            await message.delete()
        except Exception as exc:
            print(f"AJAP Liga cleanup Betis: no se pudo borrar tarjeta GES de prueba: {exc}")

    # Remove AJAP's own confirmation reaction from the original test screenshot.
    try:
        channel = guild.get_channel(int(result["source_channel_id"]))
        if channel is None:
            channel = await guild.fetch_channel(int(result["source_channel_id"]))
        message = await channel.fetch_message(int(result["source_message_id"]))
        if guild.me is not None:
            await message.remove_reaction("✅", guild.me)
    except Exception:
        pass


async def _run(runtime, bot):
    guild_id = int(guild_isolation.LEGACY_GUILD_ID)
    guild = bot.get_guild(guild_id)
    if guild is None:
        return
    try:
        result = _cleanup(runtime, guild_id)
    except Exception as exc:
        print(f"AJAP Liga cleanup Betis: {type(exc).__name__}: {exc}")
        return

    if result:
        await _cleanup_discord_artifacts(bot, guild, result)
        try:
            await league.refresh(runtime, bot, guild_id)
        except Exception:
            # The current Liga UI reads live from DB, so this is only a compatibility refresh.
            pass


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_betis_test_result_cleanup", False):
        return

    @bot.listen("on_ready")
    async def _ajap_cleanup_betis_test_result():
        await _run(runtime, bot)

    runtime._ajap_betis_test_result_cleanup = True
    print("AJAP Liga: cleanup de prueba Betis 2-0 Sevilla listo")


_ORIGINAL = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_betis_test_result_cleanup_wrapper",
    False,
):
    _apply._ajap_betis_test_result_cleanup_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
