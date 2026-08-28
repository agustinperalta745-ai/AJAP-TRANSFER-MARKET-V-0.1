"""Keep assignment history authoritative without overwriting a live club.

Rules:
- RENUNCIA_DT / DESVINCULADO_ADMIN are authoritative. If they are the newest
  audited event, the manager is free until a new audited assignment exists.
- ASIGNADO / ASIGNADO_VACANTE_ADMIN never replace an existing valid live club.
  The live `clubs` row wins while it exists.
- If the live row is missing, the newest audited assignment is the only valid
  recovery source. An older protected guard may not resurrect a previous club.
- If the buggy previous version already changed a live club, repair it once from
  the guard event it recorded before the bad overwrite.

This makes opening a fresh /mercado deterministic: it always resolves the current
assignment from the guild database + newest audited mutation, never from stale UI
or an older protected assignment.
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


def _repair_previous_active_history_overwrite(conn, user_id: int, observed):
    """Undo the exact bad write produced by the previous patch, once.

    The buggy version always wrote a guard event *before* replacing `clubs`:
    observed_club=<real live club>, protected_club=<old history club>,
    action=HISTORY_AUTHORITY_RESTORED_FROM_....

    We only reverse it when that event is still the newest guard event and the
    current row still equals the bad protected club. A later manual/admin change
    therefore wins and is never touched by this repair.
    """
    if not observed:
        return observed

    latest = conn.execute(
        """
        SELECT id, observed_club, protected_club, action
        FROM club_assignment_guard_events
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(user_id),),
    ).fetchone()
    if not latest:
        return observed

    action = str(latest["action"] or "").strip().upper()
    if not action.startswith("HISTORY_AUTHORITY_RESTORED_FROM_"):
        return observed

    previous_live = str(latest["observed_club"] or "").strip() or None
    bad_history_club = str(latest["protected_club"] or "").strip() or None
    if not previous_live or not bad_history_club:
        return observed
    if previous_live.casefold() == bad_history_club.casefold():
        return observed
    if observed.casefold() != bad_history_club.casefold():
        return observed
    if consistency._club_deleted(conn, previous_live):
        return observed

    guard = conn.execute(
        "SELECT club, active, source FROM club_assignment_guard WHERE user_id = ? LIMIT 1",
        (int(user_id),),
    ).fetchone()
    if guard is not None:
        guard_club = str(guard["club"] or "").strip() or None
        guard_source = str(guard["source"] or "").strip().upper()
        if not bool(guard["active"]):
            return observed
        if guard_club and guard_club.casefold() != bad_history_club.casefold():
            return observed
        if guard_source and not guard_source.startswith("HISTORY_AUTHORITY_"):
            return observed

    consistency._restore_club_row(conn, int(user_id), previous_live)
    consistency._set_guard(
        conn,
        int(user_id),
        previous_live,
        True,
        "REPAIR_ACTIVE_HISTORY_OVERWRITE",
        None,
    )
    consistency._event(
        conn,
        int(user_id),
        bad_history_club,
        previous_live,
        "REPAIRED_ACTIVE_HISTORY_OVERWRITE",
    )
    return previous_live


def _recover_missing_live_assignment(conn, user_id: int, history):
    """Recover a missing `clubs` row only from the newest audited assignment.

    This is the important stale-state guard: when the live row disappeared, the
    old consistency layer used to fall back to whatever club was still protected
    in `club_assignment_guard`. If that guard belonged to a previous club, opening
    /mercado could bring that previous club back. The latest active audit event is
    newer evidence and is therefore the only recovery candidate.
    """
    club = str(history["club"] or "").strip() or None
    action = str(history["action"] or "").strip().upper()
    if not club:
        return None

    if consistency._club_deleted(conn, club):
        consistency._set_guard(
            conn,
            user_id,
            club,
            False,
            "HISTORY_RECOVERY_TEAM_DELETED",
            history["actor_id"],
        )
        consistency._event(
            conn,
            user_id,
            None,
            None,
            f"BLOCKED_RECOVERY_DELETED_TEAM_AFTER_{action}",
        )
        return None

    guard = conn.execute(
        "SELECT club, active FROM club_assignment_guard WHERE user_id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    guard_club = str(guard["club"] or "").strip() if guard else None

    if (
        guard is not None
        and bool(guard["active"])
        and guard_club
        and guard_club.casefold() != club.casefold()
    ):
        consistency._event(
            conn,
            user_id,
            guard_club,
            club,
            "IGNORED_STALE_GUARD_FOR_LATEST_ASSIGNMENT",
        )

    consistency._restore_club_row(conn, user_id, club)
    consistency._set_guard(
        conn,
        user_id,
        club,
        True,
        f"HISTORY_RECOVERY_{action}",
        history["actor_id"],
    )
    consistency._event(
        conn,
        user_id,
        None,
        club,
        f"RECOVERED_MISSING_LIVE_FROM_{action}",
    )
    return club


def _history_authoritative_club(runtime, user_id: int):
    user_id = int(user_id)
    with runtime.db() as conn:
        consistency._ensure_guard_schema(conn)
        observed = consistency._observed_club(conn, user_id)
        observed = _repair_previous_active_history_overwrite(conn, user_id, observed)
        history = _recognized_history(conn, user_id)

        if history is not None and not history["active"]:
            action = history["action"]
            history_club = history["club"]

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

        if history is not None and history["active"]:
            if observed:
                # IMPORTANT: a live `clubs` row is newer operational truth than
                # an old positive history event. Never replace Aston with Ajax
                # (or any other club) merely because ASIGNADO is still the latest
                # audited row from an older workflow.
                if consistency._club_deleted(conn, observed):
                    conn.execute("DELETE FROM clubs WHERE user_id = ?", (user_id,))
                    observed = None
                else:
                    guard = conn.execute(
                        "SELECT club, active FROM club_assignment_guard WHERE user_id = ? LIMIT 1",
                        (user_id,),
                    ).fetchone()
                    guard_club = str(guard["club"] or "").strip() if guard else None
                    needs_guard_sync = (
                        guard is None
                        or not bool(guard["active"])
                        or (guard_club or "").casefold() != observed.casefold()
                    )
                    if needs_guard_sync:
                        consistency._set_guard(
                            conn,
                            user_id,
                            observed,
                            True,
                            "LIVE_CLUB_OVERRIDES_OLD_ACTIVE_HISTORY",
                            None,
                        )
                        history_club = str(history["club"] or "").strip() or None
                        if history_club and history_club.casefold() != observed.casefold():
                            consistency._event(
                                conn,
                                user_id,
                                history_club,
                                observed,
                                "IGNORED_STALE_ACTIVE_ASSIGNMENT_HISTORY",
                            )
                    return observed

            # There is no usable live row. Recover only from the newest audited
            # assignment; never from an older active guard.
            return _recover_missing_live_assignment(conn, user_id, history)

    # No recognized audited event at all: preserve the original guard's legacy
    # fallback for databases that predate assignment history.
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
        "AJAP historial de asignación v3 activo: bajas autoritativas + club vivo "
        "prioritario + recuperación solo desde la última asignación auditada"
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
