"""Make assignment history authoritative over stale protected/live club state.

This closes an intermittent case where a manager could resign correctly, open a
fresh /mercado later, and be shown as manager of the old club again. The older
assignment guard protected against silent SQL changes, but if its own row stayed
ACTIVE while club_assignment_history already contained RENUNCIA_DT, club_de()
trusted the stale guard and recreated the deleted clubs row.

The newest recognized audited assignment event now always wins:
- RENUNCIA_DT / DESVINCULADO_ADMIN => user is free, stale clubs row is deleted.
- ASIGNADO / ASIGNADO_VACANTE_ADMIN => that audited club is the live assignment.
"""

from __future__ import annotations

import club_assignment_consistency_patch as consistency
import guild_isolation_patch as guild_isolation
import team_assignment as teams


APP = None


def _recognized_history(conn, user_id: int):
    history = consistency._latest_history(conn, int(user_id))
    if not history:
        return None

    action = str(history["action"] or "").strip().upper()
    club = str(history["club"] or "").strip() or None
    if action in consistency.INACTIVE_HISTORY_ACTIONS:
        return {
            "active": False,
            "club": club,
            "action": action,
            "actor_id": history["actor_id"],
            "id": int(history["id"]),
        }
    if action in consistency.ACTIVE_HISTORY_ACTIONS and club:
        return {
            "active": True,
            "club": club,
            "action": action,
            "actor_id": history["actor_id"],
            "id": int(history["id"]),
        }
    return None


def _history_authoritative_club(runtime, user_id: int):
    user_id = int(user_id)
    with runtime.db() as conn:
        consistency._ensure_guard_schema(conn)
        observed = consistency._observed_club(conn, user_id)
        history = _recognized_history(conn, user_id)

        if history is not None:
            action = history["action"]
            history_club = history["club"]

            if not history["active"]:
                # A recorded resignation/unlink is final until a NEW assignment
                # action is audited. Never let an older ACTIVE guard resurrect it.
                if observed:
                    conn.execute("DELETE FROM clubs WHERE user_id = ?", (user_id,))
                    consistency._event(
                        conn,
                        user_id,
                        observed,
                        None,
                        f"HISTORY_AUTHORITY_REMOVED_STALE_AFTER_{action}",
                    )

                guard = conn.execute(
                    "SELECT club, active FROM club_assignment_guard WHERE user_id = ? LIMIT 1",
                    (user_id,),
                ).fetchone()
                guard_club = str(guard["club"] or "").strip() if guard else None
                if (
                    guard is None
                    or bool(guard["active"])
                    or (history_club and (guard_club or "").casefold() != history_club.casefold())
                ):
                    consistency._set_guard(
                        conn,
                        user_id,
                        history_club,
                        False,
                        f"HISTORY_AUTHORITY_{action}",
                        history["actor_id"],
                    )
                return None

            # Latest audited event is a real assignment. Honor it unless Staff
            # explicitly deleted that club.
            if consistency._club_deleted(conn, history_club):
                if observed:
                    conn.execute("DELETE FROM clubs WHERE user_id = ?", (user_id,))
                consistency._set_guard(
                    conn,
                    user_id,
                    history_club,
                    False,
                    "HISTORY_AUTHORITY_TEAM_DELETED",
                    history["actor_id"],
                )
                return None

            if not observed or observed.casefold() != history_club.casefold():
                consistency._restore_club_row(conn, user_id, history_club)
                consistency._event(
                    conn,
                    user_id,
                    observed,
                    history_club,
                    f"HISTORY_AUTHORITY_RESTORED_FROM_{action}",
                )

            guard = conn.execute(
                "SELECT club, active FROM club_assignment_guard WHERE user_id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
            guard_club = str(guard["club"] or "").strip() if guard else None
            if (
                guard is None
                or not bool(guard["active"])
                or (guard_club or "").casefold() != history_club.casefold()
            ):
                consistency._set_guard(
                    conn,
                    user_id,
                    history_club,
                    True,
                    f"HISTORY_AUTHORITY_{action}",
                    history["actor_id"],
                )
            return history_club

    # No recognized audited event: preserve the previous guard's legacy fallback.
    return consistency._guarded_club_original(runtime, user_id)


def apply_assignment_history_authority_patch(runtime, bot):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_assignment_history_authority_patch", False):
        return

    if not hasattr(consistency, "_guarded_club_original"):
        consistency._guarded_club_original = consistency._guarded_club

    consistency._guarded_club = _history_authoritative_club

    def club_de(user_id: int):
        return _history_authoritative_club(runtime, int(user_id))

    runtime.club_de = club_de
    teams.club_de = club_de

    runtime._ajap_assignment_history_authority_patch = True
    print(
        "AJAP historial de asignación autoritativo activo: una renuncia/desvinculación "
        "auditada no puede restaurar el club anterior"
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_history_authority(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_assignment_history_authority_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_assignment_history_authority_wrapped",
    False,
):
    _apply_guild_isolation_then_history_authority._ajap_assignment_history_authority_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_history_authority
