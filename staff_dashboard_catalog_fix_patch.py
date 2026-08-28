"""Keep Staff dashboard counts aligned with the real JSON-backed catalog.

The user-facing team selector and roster catalog already define the league as the
clubs backed by valid JSON files in data/. The Staff dashboard used to read every
active/legacy league_teams row directly, which could temporarily show 25 clubs
when only 23 JSON-backed clubs were selectable. It also LEFT JOINed finances and
interpreted a missing finance row as $0, creating false low-balance alerts.

Before building the Staff snapshot we now force the existing JSON catalog sync.
That sync deactivates legacy rows and seeds any missing real club finance account
with the canonical initial budget. Then this layer recomputes assignments and
low-balance alerts strictly over the active JSON-backed catalog.
"""

from __future__ import annotations

import staff_dashboard_patch as dashboard
import roster_catalog_autosync_patch as catalog


_ORIGINAL_SNAPSHOT = dashboard._staff_snapshot


def _table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table_name,),
        ).fetchone()
    )


def _staff_snapshot_synced():
    # This is the same source-of-truth sync used by the actual team selector.
    # It keeps only valid JSON-backed teams active and creates missing finance
    # rows with the configured initial budget ($10M at the time of this patch).
    try:
        catalog._sync_loaded_teams_into_catalog()
    except Exception as exc:
        print(f"WARNING AJAP dashboard: sync catálogo JSON falló: {exc}")

    data = _ORIGINAL_SNAPSHOT()
    app = dashboard.APP
    if app is None:
        return data

    try:
        with app.db() as conn:
            if not _table_exists(conn, "league_teams"):
                return data

            active_rows = conn.execute(
                """
                SELECT name
                FROM league_teams
                WHERE active=1
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()
            active_names = [str(row["name"]).strip() for row in active_rows if row["name"]]
            data["total_clubs"] = len(active_names)

            # A preserved historical/legacy assignment must not reduce the number
            # of available JSON teams shown by Staff.
            if _table_exists(conn, "clubs"):
                row = conn.execute(
                    """
                    SELECT COUNT(DISTINCT c.name) AS n
                    FROM clubs c
                    JOIN league_teams lt ON lt.name=c.name COLLATE NOCASE
                    WHERE lt.active=1
                    """
                ).fetchone()
                data["assigned"] = int(row["n"] or 0)
            else:
                data["assigned"] = 0

            # Missing finance rows are not $0 balances. Normally catalog sync
            # creates them with INITIAL_TEAM_BUDGET; INNER JOIN also prevents a
            # transient missing row from generating a false Staff alert.
            if _table_exists(conn, "club_finances"):
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM league_teams lt
                    JOIN club_finances cf ON cf.club=lt.name COLLATE NOCASE
                    WHERE lt.active=1 AND cf.balance < 1000000
                    """
                ).fetchone()
                data["low_balance"] = int(row["n"] or 0)
            else:
                data["low_balance"] = 0
    except Exception as exc:
        print(f"WARNING AJAP dashboard: corrección de catálogo parcial: {exc}")

    return data


dashboard._staff_snapshot = _staff_snapshot_synced
print(
    "AJAP dashboard Staff corregido: catálogo JSON real + asignaciones activas + "
    "alertas de saldo sin falsos $0"
)
