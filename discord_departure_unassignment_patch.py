"""Automatic AJPA cleanup when a manager leaves Discord.

The bot intentionally uses Intents.default(), so Discord's member-remove gateway
event is treated as a fast path, not the only guarantee. A conservative REST
reconciliation also checks every assigned manager on ready and every five
minutes. Only an explicit Discord 404 is considered proof that the member left.

Mobile-admin unassignments are committed by the HTTP thread and queued in a
small SQLite outbox. This Discord-side worker then removes projected roles /
nickname and publishes the normal free-team vacancy card.
"""

from __future__ import annotations

import sqlite3

import discord
from discord.ext import tasks

import club_access_revocation as access
import free_team_vacancy_patch as vacancies
import guild_isolation_patch
import team_assignment as teams


APP = None
BOT = None


def _pending_outbox(conn: sqlite3.Connection, limit: int = 25) -> list[dict]:
    access.ensure_assignment_schema(conn)
    rows = conn.execute(
        """
        SELECT id, user_id, club, source, actor_id, attempts
        FROM club_unassignment_discord_outbox
        WHERE status='PENDING'
          AND datetime(next_attempt_at) <= datetime('now')
        ORDER BY id ASC
        LIMIT ?
        """,
        (max(1, min(int(limit), 100)),),
    ).fetchall()
    return [dict(row) for row in rows]


def _mark_outbox(conn, event_id: int, status: str, error: str | None = None) -> None:
    conn.execute(
        """
        UPDATE club_unassignment_discord_outbox
        SET status=?, last_error=?, processed_at=CURRENT_TIMESTAMP
        WHERE id=? AND status='PENDING'
        """,
        (status, (str(error)[:500] if error else None), int(event_id)),
    )
    conn.commit()


def _retry_outbox(conn, event_id: int, error: str) -> None:
    conn.execute(
        """
        UPDATE club_unassignment_discord_outbox
        SET attempts=attempts+1,
            last_error=?,
            next_attempt_at=datetime('now', '+60 seconds')
        WHERE id=? AND status='PENDING'
        """,
        (str(error)[:500], int(event_id)),
    )
    conn.commit()


def _club_still_free(conn, club: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM clubs WHERE name=? COLLATE NOCASE LIMIT 1",
        (club,),
    ).fetchone() is None


async def _discord_projection_cleanup(guild: discord.Guild, user_id: int, source: str) -> None:
    # Club role + nickname projection.
    try:
        sync = getattr(APP, "sync_member_club_identity", None)
        if callable(sync):
            await sync(guild, int(user_id))
    except Exception as exc:
        print(
            "WARNING AJPA unassign identity cleanup | "
            f"guild={guild.id} user={user_id} {type(exc).__name__}: {exc}"
        )

    # Generic DT role is separate from each club role.
    try:
        import dt_role_patch

        await dt_role_patch._remove_dt(
            guild,
            int(user_id),
            reason=f"AJPA: club desasignado ({source})",
            require_config=False,
        )
    except Exception as exc:
        print(
            "WARNING AJPA unassign DT cleanup | "
            f"guild={guild.id} user={user_id} {type(exc).__name__}: {exc}"
        )


async def _process_outbox_for_guild(guild: discord.Guild) -> None:
    conn = APP.db_for_guild(guild.id)
    try:
        conn.row_factory = sqlite3.Row
        events = _pending_outbox(conn)
        conn.commit()
    finally:
        conn.close()

    for event in events:
        event_id = int(event["id"])
        user_id = int(event["user_id"])
        club = str(event["club"])
        source = str(event["source"] or "UNASSIGN")

        await _discord_projection_cleanup(guild, user_id, source)

        conn = APP.db_for_guild(guild.id)
        try:
            conn.row_factory = sqlite3.Row
            free = _club_still_free(conn, club)
        finally:
            conn.close()

        if not free:
            conn = APP.db_for_guild(guild.id)
            try:
                conn.row_factory = sqlite3.Row
                _mark_outbox(
                    conn,
                    event_id,
                    "SKIPPED_REASSIGNED",
                    "El club ya fue asignado nuevamente.",
                )
            finally:
                conn.close()
            continue

        try:
            with guild_isolation_patch.guild_context(guild.id):
                published = await vacancies._publish_vacancy(guild, club)
        except Exception as exc:
            published = False
            error = f"{type(exc).__name__}: {exc}"
        else:
            error = None if published else "No se encontró o no respondió el canal de equipos libres."

        conn = APP.db_for_guild(guild.id)
        try:
            conn.row_factory = sqlite3.Row
            if published:
                _mark_outbox(conn, event_id, "PUBLISHED")
            else:
                _retry_outbox(conn, event_id, error or "No se pudo publicar la vacante.")
        finally:
            conn.close()


async def _unassign_departed(guild: discord.Guild, user_id: int, source: str) -> str | None:
    conn = APP.db_for_guild(guild.id)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        result = access.unassign_user_in_conn(
            conn,
            int(user_id),
            actor_id=None,
            source=source,
            queue_discord=True,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    club = result.get("club")
    if club:
        print(
            "AJPA manager departure cleaned | "
            f"guild={guild.id} user={user_id} club={club} source={source} "
            f"sessions={result.get('sessions_revoked', 0)}"
        )
    return str(club) if club else None


async def _member_presence(guild: discord.Guild, user_id: int) -> bool | None:
    if guild.get_member(int(user_id)) is not None:
        return True
    try:
        await guild.fetch_member(int(user_id))
        return True
    except discord.NotFound:
        return False
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            "WARNING AJPA departure check inconclusive | "
            f"guild={guild.id} user={user_id} {type(exc).__name__}: {exc}"
        )
        return None


async def reconcile_departed_managers(guild: discord.Guild) -> int:
    conn = APP.db_for_guild(guild.id)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT user_id, name
            FROM clubs
            WHERE user_id IS NOT NULL
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
    finally:
        conn.close()

    cleaned = 0
    for row in rows:
        user_id = int(row["user_id"])
        present = await _member_presence(guild, user_id)
        if present is False:
            if await _unassign_departed(guild, user_id, "DISCORD_LEFT_RECONCILE"):
                cleaned += 1
    return cleaned


def _wrap_existing_admin_unlink() -> None:
    """Discord's existing Desvincular flow must also revoke the APK token."""
    original = teams.unlink_team
    if getattr(original, "_ajpa_mobile_access_revocation", False):
        return

    def unlink_team(user_id, admin_id):
        removed = original(user_id, admin_id)
        if removed:
            try:
                with APP.db() as conn:
                    revoked = access.revoke_mobile_access(conn, int(user_id))
                print(
                    "AJPA admin unlink revoked mobile access | "
                    f"user={int(user_id)} club={removed} sessions={revoked['sessions_revoked']}"
                )
            except Exception as exc:
                # The club unlink already succeeded. Log loudly; startup/session
                # reconciliation remains a second safety layer.
                print(
                    "WARNING AJPA admin unlink mobile revoke failed | "
                    f"user={int(user_id)} {type(exc).__name__}: {exc}"
                )
        return removed

    unlink_team._ajpa_mobile_access_revocation = True
    unlink_team._ajpa_mobile_access_revocation_base = original
    teams.unlink_team = unlink_team



def apply_discord_departure_unassignment_patch(runtime, bot) -> None:
    global APP, BOT
    if getattr(runtime, "_ajpa_departure_unassignment_patch", False):
        return

    APP = runtime
    BOT = bot
    _wrap_existing_admin_unlink()

    async def on_member_remove(member: discord.Member):
        try:
            await _unassign_departed(member.guild, int(member.id), "DISCORD_LEFT_EVENT")
        except Exception as exc:
            print(
                "WARNING AJPA member-remove cleanup failed | "
                f"guild={member.guild.id} user={member.id} {type(exc).__name__}: {exc}"
            )

    @tasks.loop(minutes=5)
    async def departure_reconcile_worker():
        if not bot.is_ready():
            return
        for guild in list(bot.guilds):
            try:
                await reconcile_departed_managers(guild)
                await _process_outbox_for_guild(guild)
            except Exception as exc:
                print(
                    "WARNING AJPA departure worker | "
                    f"guild={guild.id} {type(exc).__name__}: {exc}"
                )

    @tasks.loop(seconds=5)
    async def unassignment_outbox_worker():
        if not bot.is_ready():
            return
        for guild in list(bot.guilds):
            try:
                await _process_outbox_for_guild(guild)
            except Exception as exc:
                print(
                    "WARNING AJPA unassignment outbox | "
                    f"guild={guild.id} {type(exc).__name__}: {exc}"
                )

    async def on_ready():
        for guild in list(bot.guilds):
            try:
                cleaned = await reconcile_departed_managers(guild)
                if cleaned:
                    print(f"AJPA startup departure reconcile: guild={guild.id} cleaned={cleaned}")
                await _process_outbox_for_guild(guild)
            except Exception as exc:
                print(
                    "WARNING AJPA startup departure reconcile | "
                    f"guild={guild.id} {type(exc).__name__}: {exc}"
                )
        if not departure_reconcile_worker.is_running():
            departure_reconcile_worker.start()
        if not unassignment_outbox_worker.is_running():
            unassignment_outbox_worker.start()

    bot.add_listener(on_member_remove, "on_member_remove")
    bot.add_listener(on_ready, "on_ready")

    runtime._ajpa_departure_unassignment_patch = True
    runtime._ajpa_departure_reconcile_worker = departure_reconcile_worker
    runtime._ajpa_unassignment_outbox_worker = unassignment_outbox_worker
    print(
        "AJPA salida Discord activa: club libre + sesión Mobile revocada + "
        "reconciliación REST cada 5 minutos"
    )


_original_apply_guild_isolation_patch = guild_isolation_patch.apply_guild_isolation_patch


def _apply_guild_isolation_then_departure_cleanup(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_discord_departure_unassignment_patch(runtime, bot)


if not getattr(
    guild_isolation_patch,
    "_ajpa_departure_unassignment_wrapped",
    False,
):
    guild_isolation_patch.apply_guild_isolation_patch = (
        _apply_guild_isolation_then_departure_cleanup
    )
    guild_isolation_patch._ajpa_departure_unassignment_wrapped = True
