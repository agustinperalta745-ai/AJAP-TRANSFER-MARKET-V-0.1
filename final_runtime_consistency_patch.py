"""Final runtime consistency fixes for AJAP.

Imported before run_bot, but installed only after the last roster synchronizer
(Galatasaray) finishes. This guarantees no later market/guild/Staff wrapper can
restore stale behavior.

Final guarantees:
- ``Jugador Libre`` is a pseudo-club and never participates in the 20-player
  minimum. A free-agent signing validates only destination capacity (max 32).
- Staff dashboard counts the canonical JSON-backed clubs, including split JSON
  sources such as Galatasaray, and ignores legacy/auxiliary rows.
- RESET V1 always restores every canonical JSON club to the initial $10M budget.
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


def _canonical_json_names():
    """Same JSON source used by RESET V1, including split Galatasaray JSON."""
    import v1_official_reset_patch as reset

    names = []
    seen = set()
    for _source, payload in reset._payloads():
        club = str(payload.get("equipo") or "").strip()
        players = payload.get("jugadores") or []
        if not club or not isinstance(players, list) or not players:
            continue
        key = club.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(club)
    return names


def _resolve_club(conn, source_name):
    import roster_catalog_autosync_patch as catalog

    club = catalog._resolve_catalog_name(conn, source_name)
    if not club or catalog._is_deleted(conn, club):
        return None
    return club


def _valid_json_clubs(conn):
    clubs = []
    seen = set()
    for source_name in _canonical_json_names():
        club = _resolve_club(conn, source_name)
        if not club:
            continue
        key = club.casefold()
        if key in seen:
            continue
        seen.add(key)
        clubs.append(club)
    return clubs


def _ensure_initial_accounts(conn, clubs, initial_budget):
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
            (club, int(initial_budget)),
        )


def _install_dashboard_truth(runtime):
    import staff_dashboard_patch as dashboard
    import roster_catalog_autosync_patch as catalog
    import admin_roster_builder_patch as builder

    dashboard.APP = runtime
    current = dashboard._staff_snapshot
    if getattr(current, "_ajap_final_runtime_catalog", False):
        return

    def snapshot(_fallback=current):
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

                _ensure_initial_accounts(conn, clubs, builder.INITIAL_TEAM_BUDGET)

                tables = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                assigned = 0
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

                rows = conn.execute("SELECT club, balance FROM club_finances").fetchall()
                data["low_balance"] = sum(
                    1
                    for row in rows
                    if str(row["club"] or "").strip().casefold() in valid
                    and int(row["balance"] or 0) < 1_000_000
                )
        except Exception as exc:
            print(f"WARNING AJAP final dashboard truth: {exc}")
        return data

    snapshot._ajap_final_runtime_catalog = True
    dashboard._staff_snapshot = snapshot


def _install_reset_budget_truth(runtime):
    import v1_official_reset_patch as reset
    import admin_roster_builder_patch as builder

    current = reset._reset
    if getattr(current, "_ajap_final_runtime_budget_reset", False):
        return

    def reset_with_budget(conn, guild_id, *, force=False, admin_id=None, _fallback=current):
        applied, stats = _fallback(
            conn,
            guild_id,
            force=force,
            admin_id=admin_id,
        )
        if not applied:
            return applied, stats

        clubs = _valid_json_clubs(conn)
        _ensure_initial_accounts(conn, clubs, builder.INITIAL_TEAM_BUDGET)
        for club in clubs:
            conn.execute(
                """
                UPDATE club_finances
                SET balance=?, updated_at=CURRENT_TIMESTAMP
                WHERE club=? COLLATE NOCASE
                """,
                (int(builder.INITIAL_TEAM_BUDGET), club),
            )
        conn.commit()

        stats = dict(stats or {})
        stats["budgets"] = len(clubs)
        # The manual reset UI already exposes 'finances'. Include the budget
        # restoration there too so Staff can see that accounts were reset.
        stats["finances"] = max(int(stats.get("finances", 0)), len(clubs))
        print(
            "AJAP FINAL RESET presupuesto: "
            f"guild={guild_id} • clubes={len(clubs)} • saldo=$10.000.000"
        )
        return applied, stats

    reset_with_budget._ajap_final_runtime_budget_reset = True
    reset._reset = reset_with_budget


def install_final_runtime_consistency(runtime):
    if getattr(runtime, "_ajap_final_runtime_consistency", False):
        return False

    _install_free_agent_validator(runtime)
    _install_dashboard_truth(runtime)
    _install_reset_budget_truth(runtime)
    runtime._ajap_final_runtime_consistency = True
    print(
        "AJAP FINAL runtime fix activo: Jugador Libre sin mínimo 20 + "
        "dashboard JSON real + RESET $10M"
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
