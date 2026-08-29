"""Final runtime consistency fixes for AJAP.

This module is imported before run_bot, but wraps the last roster sync invoked by
run_bot (Galatasaray). That lets the fixes below install AFTER every market,
guild, Staff and roster layer has already been applied, preventing later wrappers
from restoring stale behavior.

Final guarantees:
- ``Jugador Libre`` is a pseudo-club and never participates in the 20-player
  minimum. A free-agent signing validates only destination capacity (max 32).
- Staff dashboard counts only valid JSON-backed clubs and only real finance rows;
  legacy/auxiliary DB rows cannot inflate available-club or low-balance alerts.
"""

from __future__ import annotations

import galatasaray_roster_patch as galatasaray


_ORIGINAL_GALATASARAY_APPLY = galatasaray.apply_galatasaray_json


def _has(row, key):
    return row is not None and key in row.keys()


def _is_free_agent_row(row):
    if not row:
        return False
    op = (
        str(row["operation_type"] or "").strip().upper()
        if _has(row, "operation_type")
        else ""
    )
    seller = str(row["seller"] or "").strip().casefold()
    return op == "JUGADOR LIBRE" or seller == "jugador libre"


def _install_free_agent_validator(runtime):
    import squad_limits_patch as squad_limits

    squad_limits.APP = runtime
    current = squad_limits.validate_rows
    if getattr(current, "_ajap_final_runtime_free_agent", False):
        return

    def validate_rows(rows, connection=None, _fallback=current):
        rows = list(rows or [])
        if not rows or not all(_is_free_agent_row(row) for row in rows):
            return _fallback(rows, connection=connection)

        own = connection is None
        conn = connection or runtime.db()
        try:
            # Jugador Libre is only a holding state. Never calculate a minimum
            # squad for it. Each destination still has to respect max 32 slots.
            for row in rows:
                buyer = str(row["buyer"] or "").strip()
                if not buyer:
                    return False, "⛔ El fichaje de agente libre no tiene club de destino."
                ok, reason = squad_limits.validate_free_agent(conn, buyer)
                if not ok:
                    return False, reason
            return True, None
        finally:
            if own:
                conn.close()

    validate_rows._ajap_final_runtime_free_agent = True
    squad_limits.validate_rows = validate_rows


def _valid_json_clubs(conn):
    import roster_catalog_autosync_patch as catalog

    clubs = []
    seen = set()
    for source_name in catalog._json_source_team_names():
        club = catalog._resolve_catalog_name(conn, source_name)
        if not club or catalog._is_deleted(conn, club):
            continue
        key = club.casefold()
        if key in seen:
            continue
        seen.add(key)
        clubs.append(club)
    return clubs


def _install_dashboard_truth(runtime):
    import staff_dashboard_patch as dashboard
    import roster_catalog_autosync_patch as catalog
    import admin_roster_builder_patch as builder

    dashboard.APP = runtime
    current = dashboard._staff_snapshot
    if getattr(current, "_ajap_final_runtime_catalog", False):
        return

    def snapshot(_fallback=current):
        # First let the normal dashboard calculate offers/operations/etc.
        try:
            catalog._sync_loaded_teams_into_catalog()
        except Exception as exc:
            print(f"WARNING AJAP final dashboard catalog sync: {exc}")

        data = _fallback()
        try:
            with runtime.db() as conn:
                clubs = _valid_json_clubs(conn)
                valid = {club.casefold() for club in clubs}
                data["total_clubs"] = len(clubs)

                # Ensure every real JSON club has its canonical starting account.
                # INSERT OR IGNORE never overwrites legitimate market balances.
                if clubs:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS club_finances (
                            club TEXT PRIMARY KEY COLLATE NOCASE,
                            balance INTEGER NOT NULL DEFAULT 0,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                    for club in clubs:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO club_finances (club, balance, updated_at)
                            VALUES (?, ?, CURRENT_TIMESTAMP)
                            """,
                            (club, int(builder.INITIAL_TEAM_BUDGET)),
                        )

                assigned = 0
                tables = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "clubs" in tables:
                    rows = conn.execute(
                        "SELECT DISTINCT name FROM clubs WHERE name IS NOT NULL"
                    ).fetchall()
                    assigned = sum(
                        1
                        for row in rows
                        if str(row["name"] or "").strip().casefold() in valid
                    )
                data["assigned"] = assigned

                # Only actual finance rows belonging to the valid JSON catalog
                # can trigger this alert. Missing/legacy rows are never treated as $0.
                low = 0
                if clubs:
                    rows = conn.execute(
                        "SELECT club, balance FROM club_finances"
                    ).fetchall()
                    low = sum(
                        1
                        for row in rows
                        if str(row["club"] or "").strip().casefold() in valid
                        and int(row["balance"] or 0) < 1_000_000
                    )
                data["low_balance"] = low
        except Exception as exc:
            print(f"WARNING AJAP final dashboard truth: {exc}")
        return data

    snapshot._ajap_final_runtime_catalog = True
    dashboard._staff_snapshot = snapshot


def install_final_runtime_consistency(runtime):
    if getattr(runtime, "_ajap_final_runtime_consistency", False):
        return False

    _install_free_agent_validator(runtime)
    _install_dashboard_truth(runtime)
    runtime._ajap_final_runtime_consistency = True
    print(
        "AJAP FINAL runtime fix activo: Jugador Libre sin mínimo 20 + "
        "dashboard limitado al catálogo JSON real"
    )
    return True


def _apply_galatasaray_then_final(runtime, *args, **kwargs):
    result = _ORIGINAL_GALATASARAY_APPLY(runtime, *args, **kwargs)
    install_final_runtime_consistency(runtime)
    return result


if not getattr(
    galatasaray.apply_galatasaray_json,
    "_ajap_final_runtime_consistency_wrapped",
    False,
):
    _apply_galatasaray_then_final._ajap_final_runtime_consistency_wrapped = True
    galatasaray.apply_galatasaray_json = _apply_galatasaray_then_final
