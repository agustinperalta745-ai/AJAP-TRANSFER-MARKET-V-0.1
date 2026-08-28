"""Reset real JSON-backed club finances to the canonical V1 starting budget.

RESET V1 is a clean-launch/reset tool, so test money must not survive it. The
core reset already restores rosters and clears market activity; this final layer
also restores every currently valid JSON-backed club to INITIAL_TEAM_BUDGET.
Legacy/non-JSON clubs are intentionally ignored because they are not part of the
23 selectable teams.
"""

from __future__ import annotations

import admin_roster_builder_patch as builder
import roster_catalog_autosync_patch as catalog
import v1_official_reset_patch as reset


_ORIGINAL_RESET = reset._reset


def _ensure_finance_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS club_finances (
            club TEXT PRIMARY KEY COLLATE NOCASE,
            balance INTEGER NOT NULL DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _restore_json_budgets(conn):
    _ensure_finance_schema(conn)
    restored = 0
    seen = set()

    for source_name in catalog._json_source_team_names():
        club = catalog._resolve_catalog_name(conn, source_name)
        if not club or catalog._is_deleted(conn, club):
            continue
        key = club.casefold()
        if key in seen:
            continue
        seen.add(key)

        conn.execute(
            """
            INSERT INTO club_finances (club, balance, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(club) DO UPDATE SET
                balance=excluded.balance,
                updated_at=CURRENT_TIMESTAMP
            """,
            (club, int(builder.INITIAL_TEAM_BUDGET)),
        )
        restored += 1

    conn.commit()
    return restored


def _reset_with_clean_budgets(conn, guild_id, *, force=False, admin_id=None):
    applied, stats = _ORIGINAL_RESET(
        conn,
        guild_id,
        force=force,
        admin_id=admin_id,
    )
    if not applied:
        return applied, stats

    budgets = _restore_json_budgets(conn)
    stats = dict(stats or {})
    stats["budgets"] = budgets
    print(
        "AJAP RESET V1 economía restaurada: "
        f"guild={guild_id} • clubes_json={budgets} • "
        f"saldo_inicial=${int(builder.INITIAL_TEAM_BUDGET):,}".replace(",", ".")
    )
    return applied, stats


reset._reset = _reset_with_clean_budgets
print(
    "AJAP RESET V1 presupuesto limpio activo: clubes JSON -> presupuesto inicial"
)
