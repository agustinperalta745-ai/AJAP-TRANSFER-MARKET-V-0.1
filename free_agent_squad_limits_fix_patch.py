"""Fix squad-limit validation for $0 free-agent signings.

``Jugador Libre`` is a pseudo-club used as the temporary owner of released
players. It must never be subject to the 20-player minimum that applies to real
clubs. A free-agent signing only needs to validate the destination club's
capacity (maximum 32 committed slots).

This patch is intentionally narrow: normal transfers, loans, exchanges and
clausulazos keep using the original global 20-32 validation unchanged.
"""

from __future__ import annotations

import squad_limits_patch as squad_limits
import released_free_agents_patch as free_agents


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


def validate_rows(rows, connection=None):
    rows = list(rows or [])
    if not rows:
        return True, None

    free_rows = [row for row in rows if _is_free_agent_row(row)]
    if not free_rows:
        return _ORIGINAL_VALIDATE_ROWS(rows, connection=connection)

    # Free-agent signings are deliberately single-player acquisitions. If a
    # future feature ever mixes them into a grouped swap/deal, fall back to the
    # original validator rather than silently changing unrelated semantics.
    if len(free_rows) != len(rows):
        return _ORIGINAL_VALIDATE_ROWS(rows, connection=connection)

    own = connection is None
    conn = connection or squad_limits.APP.db()
    try:
        for row in free_rows:
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
print(
    "AJAP fix agentes libres activo: Jugador Libre exento del mínimo 20; "
    "destino mantiene máximo 32"
)

# El dashboard Staff debe usar la misma fuente JSON-only que el selector real de
# equipos y no interpretar cuentas financieras faltantes como saldo $0.
import staff_dashboard_catalog_fix_patch  # noqa: F401,E402
