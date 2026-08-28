"""Final safety layer for released-player $0 signings.

The initial reservation already enforces the 32-player ceiling atomically. This
layer repeats that buyer-capacity check when Staff approves and when Staff applies
a JUGADOR LIBRE operation, covering the case where the destination club fills its
last roster slot after reserving the free agent but before the PES update.
"""

from __future__ import annotations

import released_free_agents_patch as free_agents
import squad_limits_patch as squad_limits
import staff_review_channel_patch as staff_review


APP = None
_ORIGINAL_APPLY = free_agents.apply_released_free_agents_patch


def _has(row, key):
    return row is not None and key in row.keys()


def _is_free_agent_row(row):
    if not row:
        return False
    operation_type = (
        str(row["operation_type"] or "").strip().upper()
        if _has(row, "operation_type")
        else ""
    )
    seller = str(row["seller"] or "").strip().casefold()
    return (
        operation_type == free_agents.FREE_AGENT_TYPE
        or seller == free_agents.FREE_AGENT_CLUB.casefold()
    )


def _validate_free_agent_capacity(transfer_id):
    rows = staff_review.market_reports._deal_rows(int(transfer_id))
    free_rows = [row for row in rows if _is_free_agent_row(row)]
    if not free_rows:
        return True, None

    with APP.db() as conn:
        for row in free_rows:
            buyer = str(row["buyer"] or "").strip()
            if not buyer:
                return False, "La operación de agente libre no tiene club de destino."
            ok, reason = squad_limits.validate_free_agent(conn, buyer)
            if not ok:
                return False, reason
    return True, None


def _install_staff_guards():
    if getattr(staff_review, "_ajap_free_agent_capacity_guard", False):
        return

    original_approve = staff_review._approve_deal
    original_apply = staff_review._apply_deal_to_pes

    def approve(transfer_id, staff_id):
        ok, reason = _validate_free_agent_capacity(transfer_id)
        if not ok:
            return False, reason
        return original_approve(transfer_id, staff_id)

    def apply_to_pes(transfer_id, staff_id):
        ok, reason = _validate_free_agent_capacity(transfer_id)
        if not ok:
            return False, reason
        return original_apply(transfer_id, staff_id)

    staff_review._approve_deal = approve
    staff_review._apply_deal_to_pes = apply_to_pes
    staff_review._ajap_free_agent_capacity_guard = True


def apply_released_free_agents_with_safety(runtime, bot=None):
    global APP
    _ORIGINAL_APPLY(runtime, bot)
    APP = runtime
    squad_limits.APP = runtime

    if getattr(runtime, "_ajap_released_free_agents_safety_patch", False):
        return

    _install_staff_guards()
    runtime._ajap_released_free_agents_safety_patch = True
    print(
        "AJAP agentes libres safety activo: límite 32 revalidado en reserva + Staff + PES"
    )


# released_free_agents_patch already wrapped split_transferibles. Its wrapper
# resolves this global function at call time, so replacing it here keeps the same
# startup hook while adding the final Staff/PES safety checks.
free_agents.apply_released_free_agents_patch = apply_released_free_agents_with_safety
