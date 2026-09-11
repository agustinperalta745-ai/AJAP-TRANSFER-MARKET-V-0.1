"""Mantiene el mercado AJPA completamente independiente del ciclo competitivo.

Cambiar Pretemporada/Temporada/Copa nunca abre ni cierra el mercado. El estado
del mercado sólo cambia mediante las acciones administrativas reales de mercado.
"""

from __future__ import annotations

import competition_cycle as cycle


def _independent_action(phase, n):
    if phase == cycle.PRESEASON:
        return {
            "key": "start_season",
            "label": f"INICIAR TEMPORADA {n}",
            "description": "Archiva la pretemporada e inicia la temporada oficial. El mercado conserva su estado actual.",
        }
    if phase == cycle.SEASON:
        return {
            "key": "season_market1",
            "label": "FINALIZAR TEMPORADA",
            "description": "Archiva la temporada y pasa a la siguiente etapa competitiva. El mercado no cambia.",
        }
    if phase == cycle.MARKET_1:
        return {
            "key": "market1_cup",
            "label": "INICIAR COPA",
            "description": "Inicia una Copa nueva. Abrir o cerrar el mercado sigue siendo una decisión manual de Staff.",
        }
    if phase == cycle.CUP:
        return {
            "key": "cup_market2",
            "label": "FINALIZAR COPA",
            "description": "Archiva la Copa y pasa a la siguiente etapa. El mercado conserva su estado actual.",
        }
    if phase == cycle.MARKET_2:
        return {
            "key": "market2_season",
            "label": f"INICIAR TEMPORADA {n + 1}",
            "description": "Inicia la siguiente temporada oficial. El mercado no cambia automáticamente.",
        }
    raise cycle.CycleError(f"Etapa inválida: {phase}")


def _independent_advance(conn, user_id, expected_phase=None):
    cycle.ensure_schema(conn)
    conn.commit()
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        conn.execute("BEGIN IMMEDIATE")
        state = conn.execute(
            "SELECT * FROM competition_cycle_state WHERE id=1"
        ).fetchone()
        if not state:
            raise cycle.CycleError("No existe el estado del ciclo.")

        phase = str(state["phase"])
        number = int(state["season_number"])
        if phase not in cycle.VALID:
            raise cycle.CycleError(f"Etapa inválida: {phase}")
        if expected_phase and str(expected_phase) != phase:
            raise cycle.CycleError(
                "La etapa cambió desde que abriste el panel. Actualizá y volvé a intentar."
            )

        competition_id = (
            int(state["competition_id"])
            if state["competition_id"] is not None
            else None
        )
        next_phase = phase
        next_number = number
        next_competition_id = None

        # IMPORTANTE: ninguna transición toca cycle._market().
        if phase == cycle.PRESEASON:
            cycle._finish(conn, competition_id)
            cycle._sync_season(conn, number)
            next_phase = cycle.SEASON
            next_competition_id = cycle._new(
                conn, "season", number, f"Temporada {number}"
            )
        elif phase == cycle.SEASON:
            cycle._finish(conn, competition_id)
            next_phase = cycle.MARKET_1
        elif phase == cycle.MARKET_1:
            next_phase = cycle.CUP
            next_competition_id = cycle._new(
                conn, "cup", number, f"Copa • Temporada {number}"
            )
        elif phase == cycle.CUP:
            cycle._finish(conn, competition_id)
            next_phase = cycle.MARKET_2
        elif phase == cycle.MARKET_2:
            next_number = number + 1
            cycle._sync_season(conn, next_number)
            next_phase = cycle.SEASON
            next_competition_id = cycle._new(
                conn, "season", next_number, f"Temporada {next_number}"
            )

        conn.execute(
            """UPDATE competition_cycle_state
               SET phase=?, season_number=?, competition_id=?, updated_by=?,
                   updated_at=CURRENT_TIMESTAMP
               WHERE id=1""",
            (
                next_phase,
                next_number,
                next_competition_id,
                int(user_id),
            ),
        )
        conn.execute(
            """INSERT INTO competition_cycle_history(
                   from_phase,to_phase,season_number,competition_id,changed_by
               ) VALUES(?,?,?,?,?)""",
            (
                phase,
                next_phase,
                next_number,
                next_competition_id,
                int(user_id),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return cycle.state_payload(conn)


def apply_competition_cycle_market_independence_patch() -> None:
    if getattr(cycle, "_ajpa_market_independent", False):
        return
    cycle._action = _independent_action
    cycle.advance = _independent_advance
    cycle._ajpa_market_independent = True
    print("AJPA ciclo: mercado desacoplado de las etapas competitivas")
