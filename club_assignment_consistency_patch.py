"""Persistent integrity guard for AJAP Discord <-> club assignments.

`clubs` is still the live assignment table, but it is no longer trusted blindly.
A protected per-user state plus `club_assignment_history` prevents migrations,
old panels or accidental SQL from silently restoring an older club.

Legitimate mutations are:
- teams.assign_team(...)
- teams.unlink_team(...)
- DT voluntary resignation

If `clubs` disagrees with the protected state, the protected state wins. On first
use for an existing database, the newest assignment-history event is preferred
over a stale row in `clubs`, so a recorded resignation/unlink cannot come back
just because an old database row survived somewhere.
"""

from __future__ import annotations

import os

import guild_isolation_patch as guild_isolation
import team_assignment as teams


APP = None

ACTIVE_HISTORY_ACTIONS = {
    "ASIGNADO",
    "ASIGNADO_VACANTE_ADMIN",
}
INACTIVE_HISTORY_ACTIONS = {
    "DESVINCULADO_ADMIN",
    "RENUNCIA_DT",
}


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _ensure_guard_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS club_assignment_guard (
            user_id INTEGER PRIMARY KEY,
            club TEXT,
            active INTEGER NOT NULL DEFAULT 0,
            revision INTEGER NOT NULL DEFAULT 1,
            source TEXT NOT NULL,
            actor_id INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS club_assignment_guard_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            observed_club TEXT,
            protected_club TEXT,
            action TEXT NOT NULL,
            railway_project_id TEXT,
            railway_service_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _event(conn, user_id: int, observed, protected, action: str):
    conn.execute(
        """
        INSERT INTO club_assignment_guard_events
            (user_id, observed_club, protected_club, action,
             railway_project_id, railway_service_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            observed,
            protected,
            str(action),
            (os.getenv("RAILWAY_PROJECT_ID") or "").strip() or None,
            (os.getenv("RAILWAY_SERVICE_ID") or "").strip() or None,
        ),
    )


def _set_guard(conn, user_id: int, club, active: bool, source: str, actor_id=None):
    _ensure_guard_schema(conn)
    conn.execute(
        """
        INSERT INTO club_assignment_guard
            (user_id, club, active, revision, source, actor_id, updated_at)
        VALUES (?, ?, ?, 1, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            club = excluded.club,
            active = excluded.active,
            revision = club_assignment_guard.revision + 1,
            source = excluded.source,
            actor_id = excluded.actor_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            int(user_id),
            str(club).strip() if club else None,
            1 if active else 0,
            str(source),
            int(actor_id) if actor_id is not None else None,
        ),
    )


def _latest_history(conn, user_id: int):
    if not _table_exists(conn, "club_assignment_history"):
        return None
    return conn.execute(
        """
        SELECT club, action, actor_id, id
        FROM club_assignment_history
        WHERE user_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (int(user_id),),
    ).fetchone()


def _club_deleted(conn, club: str) -> bool:
    if not club or not _table_exists(conn, "deleted_teams"):
        return False
    return bool(
        conn.execute(
            "SELECT 1 FROM deleted_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
            (club,),
        ).fetchone()
    )


def _observed_club(conn, user_id: int):
    row = conn.execute(
        "SELECT name FROM clubs WHERE user_id = ? LIMIT 1",
        (int(user_id),),
    ).fetchone()
    if not row:
        return None
    value = str(row["name"] or "").strip()
    return value or None


def _restore_club_row(conn, user_id: int, club: str):
    conn.execute(
        """
        INSERT INTO clubs (user_id, name)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET name = excluded.name
        """,
        (int(user_id), club),
    )


def _bootstrap_guard_from_history(conn, user_id: int, observed):
    """Create the first guard state, preferring the newest audited action."""
    history = _latest_history(conn, user_id)
    if history:
        action = str(history["action"] or "").strip().upper()
        history_club = str(history["club"] or "").strip() or None

        if action in INACTIVE_HISTORY_ACTIONS:
            if observed:
                conn.execute("DELETE FROM clubs WHERE user_id = ?", (int(user_id),))
                _event(
                    conn,
                    user_id,
                    observed,
                    None,
                    f"BOOTSTRAP_REMOVED_STALE_AFTER_{action}",
                )
            _set_guard(
                conn,
                user_id,
                history_club,
                False,
                f"HISTORY_{action}",
                history["actor_id"],
            )
            return None

        if action in ACTIVE_HISTORY_ACTIONS and history_club and not _club_deleted(conn, history_club):
            if not observed or observed.casefold() != history_club.casefold():
                _restore_club_row(conn, user_id, history_club)
                _event(
                    conn,
                    user_id,
                    observed,
                    history_club,
                    f"BOOTSTRAP_RESTORED_FROM_{action}",
                )
            _set_guard(
                conn,
                user_id,
                history_club,
                True,
                f"HISTORY_{action}",
                history["actor_id"],
            )
            return history_club

    # Old databases may predate assignment history. Preserve their current row
    # once, then protect it from silent changes from this point forward.
    if observed and not _club_deleted(conn, observed):
        _set_guard(conn, user_id, observed, True, "BASELINE_EXISTING_CLUB")
        return observed

    if observed:
        conn.execute("DELETE FROM clubs WHERE user_id = ?", (int(user_id),))
    return None


def _guarded_club(runtime, user_id: int):
    with runtime.db() as conn:
        _ensure_guard_schema(conn)
        observed = _observed_club(conn, user_id)
        guard = conn.execute(
            "SELECT * FROM club_assignment_guard WHERE user_id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()

        if guard is None:
            return _bootstrap_guard_from_history(conn, user_id, observed)

        protected = str(guard["club"] or "").strip() or None
        active = bool(guard["active"])

        # A Staff team deletion is a legitimate higher-level mutation. Never
        # resurrect an assignment to a club explicitly deleted by Staff.
        if active and protected and _club_deleted(conn, protected):
            if observed:
                conn.execute("DELETE FROM clubs WHERE user_id = ?", (int(user_id),))
            _set_guard(conn, user_id, protected, False, "TEAM_DELETED")
            _event(conn, user_id, observed, None, "RELEASED_DELETED_TEAM")
            return None

        if active and protected:
            if not observed or observed.casefold() != protected.casefold():
                _restore_club_row(conn, user_id, protected)
                _event(conn, user_id, observed, protected, "BLOCKED_SILENT_ASSIGNMENT_ROLLBACK")
            return protected

        # Guard says the manager is free. A row appearing in `clubs` without a
        # legitimate assignment action is stale/unauthorized and is removed.
        if observed:
            conn.execute("DELETE FROM clubs WHERE user_id = ?", (int(user_id),))
            _event(conn, user_id, observed, protected, "BLOCKED_SILENT_REASSIGNMENT")
        return None


def apply_club_assignment_consistency_patch(runtime, bot):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_club_assignment_consistency_patch_v2", False):
        return

    def club_de(user_id: int):
        return _guarded_club(runtime, int(user_id))

    def assignments():
        # Heal every currently visible row before returning the assignment list.
        with runtime.db() as conn:
            rows = conn.execute("SELECT user_id FROM clubs ORDER BY user_id").fetchall()
        for row in rows:
            _guarded_club(runtime, int(row["user_id"]))
        with runtime.db() as conn:
            return conn.execute(
                "SELECT user_id, name FROM clubs ORDER BY name COLLATE NOCASE"
            ).fetchall()

    # Wrap all legitimate assignment mutations so they advance the protected
    # state immediately. Existing UI classes resolve these functions dynamically.
    original_assign_team = teams.assign_team
    if not getattr(original_assign_team, "_ajap_assignment_guard_v2", False):
        def assign_team(user_id, team_name):
            ok, result = original_assign_team(user_id, team_name)
            if ok:
                with runtime.db() as conn:
                    _set_guard(
                        conn,
                        int(user_id),
                        result,
                        True,
                        "ASSIGN_TEAM",
                        int(user_id),
                    )
                    _event(conn, int(user_id), result, result, "LEGITIMATE_ASSIGNMENT")
            return ok, result

        assign_team._ajap_assignment_guard_v2 = True
        teams.assign_team = assign_team

    original_unlink_team = teams.unlink_team
    if not getattr(original_unlink_team, "_ajap_assignment_guard_v2", False):
        def unlink_team(user_id, admin_id):
            removed = original_unlink_team(user_id, admin_id)
            if removed:
                with runtime.db() as conn:
                    _set_guard(
                        conn,
                        int(user_id),
                        removed,
                        False,
                        "UNLINK_TEAM",
                        int(admin_id),
                    )
                    _event(conn, int(user_id), removed, None, "LEGITIMATE_ADMIN_UNLINK")
            return removed

        unlink_team._ajap_assignment_guard_v2 = True
        teams.unlink_team = unlink_team

    # Voluntary resignation deletes `clubs` directly, so protect that mutation too.
    try:
        import dt_resignation_patch as resignation

        original_resign = resignation._resign_assignment
        if not getattr(original_resign, "_ajap_assignment_guard_v2", False):
            def resign_assignment(user_id: int, expected_club: str):
                removed = original_resign(user_id, expected_club)
                if removed:
                    with runtime.db() as conn:
                        _set_guard(
                            conn,
                            int(user_id),
                            removed,
                            False,
                            "RENUNCIA_DT",
                            int(user_id),
                        )
                        _event(conn, int(user_id), removed, None, "LEGITIMATE_RESIGNATION")
                return removed

            resign_assignment._ajap_assignment_guard_v2 = True
            resignation._resign_assignment = resign_assignment
    except Exception as exc:
        print(f"WARNING AJAP assignment guard: no se pudo envolver renuncia: {exc}")

    runtime.club_de = club_de
    teams.club_de = club_de
    teams.assignments = assignments

    runtime._ajap_club_assignment_consistency_patch = True
    runtime._ajap_club_assignment_consistency_patch_v2 = True
    print(
        "AJAP assignment guard v2 activo: historial + estado protegido + "
        "bloqueo de rollback/reasignación silenciosa"
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_assignment_consistency(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_club_assignment_consistency_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_club_assignment_consistency_wrapped_v2",
    False,
):
    _apply_guild_isolation_then_assignment_consistency._ajap_club_assignment_consistency_wrapped_v2 = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_assignment_consistency
