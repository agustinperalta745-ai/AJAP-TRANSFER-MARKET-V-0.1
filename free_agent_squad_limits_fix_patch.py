"""Definitive Staff/PES fix for $0 free-agent signings.

``Jugador Libre`` is a pseudo-club/state, never a real squad. It must not be
subject to AJAP's 20-player minimum. This module fixes the generic validator and
also installs a final Staff/PES bypass so a later wrapper cannot accidentally
re-introduce the seller-minimum check.

For JUGADOR LIBRE operations we validate only:
- player is still actually in Jugador Libre;
- destination club exists;
- destination has room under the 32 committed-slot ceiling.

All normal transfers, loans, swaps and clausulazos keep the original 20-32
validation chain unchanged.
"""

from __future__ import annotations

import squad_limits_patch as squad_limits
import released_free_agents_patch as free_agents
import staff_review_channel_patch as staff_review


_ORIGINAL_VALIDATE_ROWS = squad_limits.validate_rows


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
    return (
        op == free_agents.FREE_AGENT_TYPE
        or seller == free_agents.FREE_AGENT_CLUB.casefold()
    )


def _all_free_agent(rows):
    rows = list(rows or [])
    return bool(rows) and all(_is_free_agent_row(row) for row in rows)


def validate_rows(rows, connection=None):
    """Generic backstop: only the destination matters for a free agent."""
    rows = list(rows or [])
    if not rows:
        return True, None
    if not _all_free_agent(rows):
        return _ORIGINAL_VALIDATE_ROWS(rows, connection=connection)

    own = connection is None
    conn = connection or squad_limits.APP.db()
    try:
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


squad_limits.validate_rows = validate_rows


def _deal_rows(transfer_id):
    return staff_review.market_reports._deal_rows(int(transfer_id))


def _runtime():
    return staff_review.APP or squad_limits.APP or free_agents.APP


def _validate_staff_free_agent(rows):
    if not _all_free_agent(rows):
        return False, None

    app = _runtime()
    if app is None:
        return True, "El runtime de AJAP todavía no está disponible."

    with app.db() as conn:
        for row in rows:
            buyer = str(row["buyer"] or "").strip()
            if not buyer:
                return True, "La operación de agente libre no tiene club de destino."

            if row["player_id"]:
                player = conn.execute(
                    "SELECT * FROM roster_players WHERE id=? LIMIT 1",
                    (int(row["player_id"]),),
                ).fetchone()
            else:
                player = conn.execute(
                    "SELECT * FROM roster_players WHERE name=? COLLATE NOCASE LIMIT 1",
                    (row["player"],),
                ).fetchone()

            if not player:
                return True, f"No se encontró **{row['player']}** en el plantel oficial."
            if str(player["club"] or "").casefold() != free_agents.FREE_AGENT_CLUB.casefold():
                return True, (
                    f"**{row['player']}** ya no figura como **{free_agents.FREE_AGENT_CLUB}** "
                    f"(figura en **{player['club']}**)."
                )

            ok, reason = squad_limits.validate_free_agent(conn, buyer)
            if not ok:
                return True, reason

    return True, None


def _approve_free_agent(transfer_id, staff_id):
    rows = _deal_rows(transfer_id)
    handled, error = _validate_staff_free_agent(rows)
    if not handled:
        return None
    if error:
        return False, error
    if not all((row["status"] or "").upper() == "PENDIENTE_ADMIN" for row in rows):
        return False, "La operación ya no está pendiente de aprobación."

    ids = [int(row["id"]) for row in rows]
    placeholders = ",".join("?" for _ in ids)
    app = _runtime()
    with app.db() as conn:
        conn.execute(
            f"""
            UPDATE transfers
            SET status='APROBADA', approved_by=?, approved_at=CURRENT_TIMESTAMP
            WHERE id IN ({placeholders}) AND status='PENDIENTE_ADMIN'
            """,
            (int(staff_id), *ids),
        )
    return True, None


def _apply_free_agent_to_pes(transfer_id, staff_id):
    rows = _deal_rows(transfer_id)
    handled, error = _validate_staff_free_agent(rows)
    if not handled:
        return None
    if error:
        return False, error

    statuses = {(row["status"] or "").upper() for row in rows}
    if statuses == {"APLICADA"}:
        staff_review.market_reports._mark_deal_loaded(transfer_id, staff_id)
        return True, None
    if statuses != {"APROBADA"}:
        return False, "Primero debe aprobarse el fichaje de agente libre."

    app = _runtime()
    conn = app.db()
    try:
        conn.execute("BEGIN IMMEDIATE")

        for row in rows:
            if row["player_id"]:
                player = conn.execute(
                    "SELECT * FROM roster_players WHERE id=? LIMIT 1",
                    (int(row["player_id"]),),
                ).fetchone()
            else:
                player = conn.execute(
                    "SELECT * FROM roster_players WHERE name=? COLLATE NOCASE LIMIT 1",
                    (row["player"],),
                ).fetchone()

            if not player or str(player["club"] or "").casefold() != free_agents.FREE_AGENT_CLUB.casefold():
                conn.rollback()
                current = player["club"] if player else "desconocido"
                return False, f"{row['player']} figura en {current}; no se aplicó ningún movimiento."

            buyer = str(row["buyer"] or "").strip()
            ok, reason = squad_limits.validate_free_agent(conn, buyer)
            if not ok:
                conn.rollback()
                return False, reason

        for row in rows:
            if row["player_id"]:
                player = conn.execute(
                    "SELECT * FROM roster_players WHERE id=? LIMIT 1",
                    (int(row["player_id"]),),
                ).fetchone()
            else:
                player = conn.execute(
                    "SELECT * FROM roster_players WHERE name=? COLLATE NOCASE LIMIT 1",
                    (row["player"],),
                ).fetchone()

            conn.execute(
                "UPDATE roster_players SET club=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (row["buyer"], int(player["id"])),
            )
            conn.execute(
                """
                UPDATE transfers
                SET status='APLICADA', applied_by=?, applied_at=CURRENT_TIMESTAMP,
                    pes_loaded_by=?, pes_loaded_at=COALESCE(pes_loaded_at,CURRENT_TIMESTAMP)
                WHERE id=?
                """,
                (int(staff_id), int(staff_id), int(row["id"])),
            )

            history = conn.execute(
                "SELECT id FROM player_history WHERE transfer_id=? LIMIT 1",
                (int(row["id"]),),
            ).fetchone()
            if not history:
                conn.execute(
                    """
                    INSERT INTO player_history
                    (player_id, player, from_club, to_club, transfer_id, season_id, event_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(player["id"]), row["player"], free_agents.FREE_AGENT_CLUB,
                        row["buyer"], int(row["id"]), row["season_id"],
                        free_agents.FREE_AGENT_TYPE,
                    ),
                )

        conn.commit()
        return True, None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def install_final_staff_fix():
    """Install outside whatever Staff wrappers exist at this moment."""
    current_approve = staff_review._approve_deal
    current_apply = staff_review._apply_deal_to_pes

    if getattr(current_approve, "_ajap_free_agent_final", False) and getattr(
        current_apply, "_ajap_free_agent_final", False
    ):
        return False

    def approve(transfer_id, staff_id, _fallback=current_approve):
        result = _approve_free_agent(transfer_id, staff_id)
        if result is not None:
            return result
        return _fallback(transfer_id, staff_id)

    def apply_to_pes(transfer_id, staff_id, _fallback=current_apply):
        result = _apply_free_agent_to_pes(transfer_id, staff_id)
        if result is not None:
            return result
        return _fallback(transfer_id, staff_id)

    approve._ajap_free_agent_final = True
    apply_to_pes._ajap_free_agent_final = True
    staff_review._approve_deal = approve
    staff_review._apply_deal_to_pes = apply_to_pes
    print(
        "AJAP FIX FINAL agentes libres: Staff/PES ignora mínimo de Jugador Libre; "
        "solo valida máximo 32 del destino"
    )
    return True


# Current import order.
install_final_staff_fix()

# Import-order proofing: if the generic squad-limit layer wraps Staff later,
# reinstall this bypass outside it immediately afterwards.
_original_apply_squad_limits = squad_limits.apply_squad_limits_patch


def _apply_squad_limits_then_free_agent_fix(runtime, bot=None):
    result = _original_apply_squad_limits(runtime, bot)
    install_final_staff_fix()
    return result


if not getattr(squad_limits.apply_squad_limits_patch, "_ajap_free_agent_final_wrapped", False):
    _apply_squad_limits_then_free_agent_fix._ajap_free_agent_final_wrapped = True
    squad_limits.apply_squad_limits_patch = _apply_squad_limits_then_free_agent_fix

print(
    "AJAP fix agentes libres activo: Jugador Libre exento del mínimo 20; "
    "destino mantiene máximo 32"
)

# El dashboard Staff debe usar la misma fuente JSON-only que el selector real de
# equipos y no interpretar cuentas financieras faltantes como saldo $0.
import staff_dashboard_catalog_fix_patch  # noqa: F401,E402

# RESET V1 también devuelve la economía de los clubes JSON al presupuesto
# inicial, para que ningún saldo de pruebas sobreviva a un reseteo total.
import v1_reset_finance_baseline_patch  # noqa: F401,E402
