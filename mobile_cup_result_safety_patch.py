"""Safety guard for cup score corrections.

Editing a score while keeping the same winner is allowed even if that winner has
already played the next round. In that case propagation must not clear/rewrite a
finished downstream match. Winner-changing edits are still rejected by the main
cup API whenever a dependent match has already been played.
"""

from __future__ import annotations

import mobile_cup_tournaments_api_patch as cups


def apply_mobile_cup_result_safety_patch() -> None:
    if getattr(cups, "_ajpa_result_safety_patch", False):
        return

    def safe_set_team_slot(conn, match_id: int, field: str, team: str | None) -> None:
        if field not in {"home_team", "away_team"}:
            raise ValueError("invalid slot")
        row = conn.execute("SELECT * FROM cup_matches WHERE id=? LIMIT 1", (int(match_id),)).fetchone()
        if not row:
            return
        current = str(row[field] or "") or None
        finished = str(row["status"] or "") == "FINISHED"
        # A score-only correction must never erase or downgrade a downstream game
        # that was already completed. Identity-changing corrections are blocked by
        # _validate_change_dependencies before propagation reaches this function.
        if finished:
            if team is None or (current and team and current.casefold() == str(team).casefold()):
                return
        other_field = "away_team" if field == "home_team" else "home_team"
        other = str(row[other_field] or "") or None
        status = "READY" if team and other else "PENDING"
        conn.execute(
            f"UPDATE cup_matches SET {field}=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (team, status, int(match_id)),
        )

    cups._set_team_slot = safe_set_team_slot
    cups._ajpa_result_safety_patch = True
    print("AJPA cups: downstream result safety guard enabled")
