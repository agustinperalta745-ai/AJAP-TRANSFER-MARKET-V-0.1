"""Discord bridge for club resignations performed from AJPA Mobile.

The mobile HTTP handler never performs Discord network I/O. Instead, it commits a
small outbox event together with the club release. This worker consumes that
outbox after Discord is connected and reuses the canonical vacancy publication
flow, giving mobile resignations the same public vacancy card as Discord ones.
"""

from __future__ import annotations

import sqlite3

from discord.ext import tasks

import free_team_vacancy_patch as vacancies
import guild_isolation_patch
import mobile_resignation_api_patch

APP = None
BOT = None


def _pending_events(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    mobile_resignation_api_patch.ensure_discord_outbox(conn)
    rows = conn.execute(
        """
        SELECT id, user_id, club, attempts
        FROM mobile_resignation_discord_outbox
        WHERE status='PENDING'
          AND datetime(next_attempt_at) <= datetime('now')
        ORDER BY id ASC
        LIMIT ?
        """,
        (max(1, min(int(limit), 100)),),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "user_id": int(row["user_id"]),
            "club": str(row["club"]),
            "attempts": int(row["attempts"] or 0),
        }
        for row in rows
    ]


def _club_is_still_free(conn: sqlite3.Connection, club: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM clubs WHERE name=? COLLATE NOCASE LIMIT 1",
        (club,),
    ).fetchone()
    return row is None


def _mark_processed(
    conn: sqlite3.Connection,
    event_id: int,
    status: str,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE mobile_resignation_discord_outbox
        SET status=?,
            last_error=?,
            processed_at=CURRENT_TIMESTAMP
        WHERE id=? AND status='PENDING'
        """,
        (status, error, int(event_id)),
    )
    conn.commit()


def _mark_retry(conn: sqlite3.Connection, event_id: int, error: str) -> None:
    conn.execute(
        """
        UPDATE mobile_resignation_discord_outbox
        SET attempts=attempts+1,
            last_error=?,
            next_attempt_at=datetime('now', '+60 seconds')
        WHERE id=? AND status='PENDING'
        """,
        (str(error)[:500], int(event_id)),
    )
    conn.commit()


async def sync_guild(guild) -> None:
    if APP is None:
        return

    # Snapshot DB rows first. Never keep a SQLite connection open across an
    # awaited Discord request.
    conn = APP.db_for_guild(guild.id)
    try:
        conn.row_factory = sqlite3.Row
        events = _pending_events(conn)
        conn.commit()
    finally:
        conn.close()

    for event in events:
        event_id = int(event["id"])
        club = str(event["club"])

        conn = APP.db_for_guild(guild.id)
        try:
            conn.row_factory = sqlite3.Row
            if not _club_is_still_free(conn, club):
                _mark_processed(
                    conn,
                    event_id,
                    "SKIPPED_REASSIGNED",
                    "El club ya tenía un nuevo DT antes de publicar la vacante.",
                )
                continue
        finally:
            conn.close()

        try:
            # Vacancy helpers use runtime.db(), which is guild-scoped through a
            # context variable. Preserve the correct guild while Discord awaits.
            with guild_isolation_patch.guild_context(guild.id):
                published = await vacancies._publish_vacancy(guild, club)
        except Exception as exc:
            published = False
            error = f"{type(exc).__name__}: {exc}"
        else:
            error = None if published else "No se encontró o no respondió el canal de vacantes."

        conn = APP.db_for_guild(guild.id)
        try:
            conn.row_factory = sqlite3.Row
            if published:
                _mark_processed(conn, event_id, "PUBLISHED")
            else:
                _mark_retry(conn, event_id, error or "No se pudo publicar la vacante.")
        finally:
            conn.close()


def apply_mobile_resignation_discord_bridge(runtime, bot) -> None:
    global APP, BOT
    if getattr(runtime, "_ajpa_mobile_resignation_discord_bridge", False):
        return

    APP = runtime
    BOT = bot

    @tasks.loop(seconds=5)
    async def mobile_resignation_worker():
        if not bot.is_ready():
            return
        for guild in list(bot.guilds):
            try:
                await sync_guild(guild)
            except Exception as exc:
                print(
                    "AJPA mobile resignation bridge error | "
                    f"guild={getattr(guild, 'id', '?')} | "
                    f"{type(exc).__name__}: {exc}"
                )

    async def on_ready():
        for guild in list(bot.guilds):
            try:
                await sync_guild(guild)
            except Exception as exc:
                print(
                    "AJPA mobile resignation initial sync error | "
                    f"guild={getattr(guild, 'id', '?')} | "
                    f"{type(exc).__name__}: {exc}"
                )
        if not mobile_resignation_worker.is_running():
            mobile_resignation_worker.start()

    bot.add_listener(on_ready, "on_ready")
    runtime._ajpa_mobile_resignation_discord_bridge = True
    runtime._ajpa_mobile_resignation_discord_worker = mobile_resignation_worker
    print("AJPA: mobile resignation -> Discord vacancy bridge enabled")


# bot.py imports this module before it captures the guild-isolation installer.
# Wrapping the current installer guarantees the vacancy runtime is initialized
# first, then installs this bridge on top of it.
_original_apply_guild_isolation_patch = guild_isolation_patch.apply_guild_isolation_patch


def _apply_guild_isolation_then_mobile_resignation_bridge(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_mobile_resignation_discord_bridge(runtime, bot)


if not getattr(
    guild_isolation_patch,
    "_ajpa_mobile_resignation_bridge_wrapped",
    False,
):
    guild_isolation_patch.apply_guild_isolation_patch = (
        _apply_guild_isolation_then_mobile_resignation_bridge
    )
    guild_isolation_patch._ajpa_mobile_resignation_bridge_wrapped = True
