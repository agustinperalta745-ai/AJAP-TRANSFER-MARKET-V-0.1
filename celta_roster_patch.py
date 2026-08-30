"""Replace Celta de Vigo and AS Roma with AS Monaco and Feyenoord.

This module intentionally keeps the legacy ``apply_celta_json`` entry point because
run_bot.py already calls it. Its behavior is now the official 2026-08-30 team
replacement migration:
- AS Monaco and Feyenoord are enabled/synced from their JSON sources.
- Celta de Vigo and AS Roma are removed from the active catalog.
- Current rosters/assignments/market rows that still belong to the retired teams
  are removed per guild, while transfer/history audit rows are preserved.
"""

from __future__ import annotations

import team_assignment as teams

from feyenoord_roster_patch import apply_feyenoord_json
from monaco_roster_patch import apply_monaco_json

REMOVED_TEAMS = ("Celta de Vigo", "AS Roma")
MIGRATION_MARKER = "replace_celta_roma_with_monaco_feyenoord_20260830"


def _remove_from_memory_catalog() -> None:
    retired = {name.casefold() for name in REMOVED_TEAMS}
    teams.OFFICIAL_TEAMS[:] = [
        (name, country)
        for name, country in teams.OFFICIAL_TEAMS
        if name.casefold() not in retired
    ]
    for name in REMOVED_TEAMS:
        teams.OFFICIAL.pop(name.casefold(), None)


_remove_from_memory_catalog()


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _columns(conn, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    safe = table.replace('"', '""')
    return {
        str(row["name"])
        for row in conn.execute(f'PRAGMA table_info("{safe}")').fetchall()
    }


def _delete_by_player_ids(conn, table: str, player_ids: list[int]) -> None:
    if not player_ids or not _table_exists(conn, table):
        return
    if "player_id" not in _columns(conn, table):
        return
    marks = ",".join("?" for _ in player_ids)
    safe = table.replace('"', '""')
    conn.execute(
        f'DELETE FROM "{safe}" WHERE player_id IN ({marks})',
        tuple(player_ids),
    )


def _delete_by_club_columns(conn, table: str, club: str) -> None:
    if not _table_exists(conn, table):
        return
    cols = _columns(conn, table)
    candidates = (
        "club",
        "seller",
        "buyer",
        "from_club",
        "to_club",
        "lender_club",
        "borrower_club",
        "owner_club",
        "source_club",
        "destination_club",
        "team",
    )
    club_cols = [column for column in candidates if column in cols]
    if not club_cols:
        return
    safe = table.replace('"', '""')
    where = " OR ".join(
        f'"{column.replace(chr(34), chr(34) * 2)}" = ? COLLATE NOCASE'
        for column in club_cols
    )
    conn.execute(
        f'DELETE FROM "{safe}" WHERE {where}',
        tuple(club for _ in club_cols),
    )


def _cleanup_connection(conn) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seed_state (
            key TEXT PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deleted_teams (
            name TEXT PRIMARY KEY COLLATE NOCASE,
            deleted_by INTEGER,
            deleted_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    done = conn.execute(
        "SELECT 1 FROM seed_state WHERE key = ? LIMIT 1",
        (MIGRATION_MARKER,),
    ).fetchone()
    if done:
        # Defensive guard: old static/catalog code must never reactivate them.
        if _table_exists(conn, "league_teams"):
            for club in REMOVED_TEAMS:
                conn.execute(
                    "UPDATE league_teams SET active = 0 WHERE name = ? COLLATE NOCASE",
                    (club,),
                )
        return 0

    removed_players = 0
    for club in REMOVED_TEAMS:
        player_ids: list[int] = []
        if _table_exists(conn, "roster_players"):
            rows = conn.execute(
                "SELECT id FROM roster_players WHERE club = ? COLLATE NOCASE",
                (club,),
            ).fetchall()
            player_ids = [int(row["id"]) for row in rows]
            removed_players += len(player_ids)

        # Remove live/current state tied to retired teams. Historical completed
        # transfers/player_history are intentionally kept as an audit trail.
        if _table_exists(conn, "clubs"):
            conn.execute(
                "DELETE FROM clubs WHERE name = ? COLLATE NOCASE",
                (club,),
            )

        for table in (
            "publications",
            "offers",
            "loans",
            "clause_requests",
            "free_team_requests",
            "vacancy_requests",
        ):
            _delete_by_club_columns(conn, table, club)

        if _table_exists(conn, "club_finances"):
            _delete_by_club_columns(conn, "club_finances", club)

        for table in (
            "player_rating_inputs",
            "pes6_player_attributes",
            "pes6_attributes",
            "player_attributes",
            "pes6_player_special_abilities",
        ):
            _delete_by_player_ids(conn, table, player_ids)

        if _table_exists(conn, "roster_players"):
            conn.execute(
                "DELETE FROM roster_players WHERE club = ? COLLATE NOCASE",
                (club,),
            )

        if _table_exists(conn, "league_teams"):
            conn.execute(
                "UPDATE league_teams SET active = 0 WHERE name = ? COLLATE NOCASE",
                (club,),
            )

        conn.execute(
            """
            INSERT INTO deleted_teams (name, deleted_by, deleted_at)
            VALUES (?, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                deleted_by = NULL,
                deleted_at = CURRENT_TIMESTAMP
            """,
            (club,),
        )

    conn.execute(
        "INSERT OR IGNORE INTO seed_state (key) VALUES (?)",
        (MIGRATION_MARKER,),
    )
    return removed_players


def apply_team_replacements(runtime) -> None:
    if getattr(runtime, "_ajap_monaco_feyenoord_replacement", False):
        return

    # These wrappers preserve transferred players and synchronize the uploaded
    # JSON data independently for every guild database.
    apply_monaco_json(runtime)
    apply_feyenoord_json(runtime)

    base_db = runtime.db
    cleaned_guilds: set[int] = set()

    def replacement_synced_db():
        conn = base_db()
        guild_id = int(runtime.current_guild_id())
        if guild_id in cleaned_guilds:
            return conn
        try:
            removed = _cleanup_connection(conn)
            conn.commit()
            cleaned_guilds.add(guild_id)
            print(
                "AJAP reemplazo de clubes aplicado: "
                f"guild={guild_id} • AS Monaco + Feyenoord activos • "
                f"Celta de Vigo + AS Roma retirados • {removed} jugadores viejos removidos"
            )
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = replacement_synced_db
    runtime._ajap_monaco_feyenoord_replacement = True
    print(
        "AJAP migración de reemplazo activa: "
        "AS Monaco + Feyenoord reemplazan Celta de Vigo + AS Roma"
    )


# Backward-compatible entry point used by the current run_bot.py.
def apply_celta_json(runtime) -> None:
    apply_team_replacements(runtime)
