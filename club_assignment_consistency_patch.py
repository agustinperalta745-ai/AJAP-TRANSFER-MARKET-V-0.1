"""AJAP club-assignment consistency fix.

The persistent `clubs` table is the source of truth for whether a Discord user
has a club in the current guild database. Team catalogs and Discord nicknames
are presentation/selection layers only and must never make an existing
assignment appear missing.
"""

from __future__ import annotations

import guild_isolation_patch as guild_isolation
import team_assignment as teams


APP = None


def apply_club_assignment_consistency_patch(runtime, bot):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_club_assignment_consistency_patch", False):
        return

    def club_de(user_id: int):
        with runtime.db() as conn:
            row = conn.execute(
                "SELECT name FROM clubs WHERE user_id = ? LIMIT 1",
                (int(user_id),),
            ).fetchone()
        if not row:
            return None
        name = str(row["name"] or "").strip()
        return name or None

    def assignments():
        with runtime.db() as conn:
            return conn.execute(
                "SELECT user_id, name FROM clubs ORDER BY name COLLATE NOCASE"
            ).fetchall()

    # Every later UI layer resolves these functions dynamically, so replacing
    # both references keeps MI CLUB, Staff user mode, nicknames and assignment
    # management consistent with the same per-guild SQLite database.
    runtime.club_de = club_de
    teams.club_de = club_de
    teams.assignments = assignments

    runtime._ajap_club_assignment_consistency_patch = True
    print("AJAP: asignación de club usa clubs como fuente única de verdad")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_assignment_consistency(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_club_assignment_consistency_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_club_assignment_consistency_wrapped",
    False,
):
    _apply_guild_isolation_then_assignment_consistency._ajap_club_assignment_consistency_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_assignment_consistency
