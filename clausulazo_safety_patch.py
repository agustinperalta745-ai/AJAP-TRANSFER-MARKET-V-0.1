import discord

import clausulazo_patch as clausulas


def _apply_existing_approved_clause(runtime, request_id: int):
    """Repara clausulazos ya aprobados que todavía no movieron al jugador de plantilla."""
    conn = runtime.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        req = conn.execute(
            "SELECT * FROM clause_requests WHERE id = ? AND status = 'APROBADO'",
            (request_id,),
        ).fetchone()
        if not req:
            conn.rollback()
            return False

        player = conn.execute(
            "SELECT * FROM roster_players WHERE id = ?",
            (req["player_id"],),
        ).fetchone()
        if not player:
            conn.rollback()
            return False

        current_club = (player["club"] or "").strip().casefold()
        seller_club = (req["seller_club"] or "").strip().casefold()
        buyer_club = (req["buyer_club"] or "").strip().casefold()

        # Nunca pisamos un movimiento posterior hacia un tercer club.
        if current_club not in {seller_club, buyer_club}:
            conn.rollback()
            return False

        if current_club == seller_club:
            conn.execute(
                "UPDATE roster_players SET club = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (req["buyer_club"], req["player_id"]),
            )

        if req["transfer_id"]:
            conn.execute(
                """
                UPDATE transfers
                SET status = 'APLICADA',
                    applied_by = COALESCE(applied_by, ?),
                    applied_at = COALESCE(applied_at, CURRENT_TIMESTAMP)
                WHERE id = ?
                """,
                (req["decided_by"], req["transfer_id"]),
            )
            history = conn.execute(
                "SELECT id FROM player_history WHERE transfer_id = ? LIMIT 1",
                (req["transfer_id"],),
            ).fetchone()
            if not history:
                conn.execute(
                    """
                    INSERT INTO player_history
                    (player_id, player, from_club, to_club, transfer_id, season_id, event_type)
                    VALUES (?, ?, ?, ?, ?, ?, 'CLAUSULAZO')
                    """,
                    (
                        req["player_id"],
                        req["player"],
                        req["seller_club"],
                        req["buyer_club"],
                        req["transfer_id"],
                        req["season_id"],
                    ),
                )

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _reconcile_approved_clauses(runtime):
    with runtime.db() as conn:
        rows = conn.execute(
            "SELECT id FROM clause_requests WHERE status = 'APROBADO' ORDER BY id"
        ).fetchall()

    repaired = 0
    for row in rows:
        if _apply_existing_approved_clause(runtime, row["id"]):
            repaired += 1
    return repaired


def _build_atomic_approve(runtime):
    def approve_request(req, staff_id):
        conn = runtime.db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            fresh = conn.execute(
                "SELECT * FROM clause_requests WHERE id = ?",
                (req["id"],),
            ).fetchone()
            if not fresh or fresh["status"] != "PENDIENTE_STAFF":
                conn.rollback()
                return False, "La solicitud ya fue resuelta."

            player = conn.execute(
                "SELECT * FROM roster_players WHERE id = ?",
                (fresh["player_id"],),
            ).fetchone()
            if not player or player["club"].casefold() != fresh["seller_club"].casefold():
                conn.rollback()
                clausulas.reject_request(
                    fresh,
                    staff_id,
                    "El jugador cambió de club antes de la aprobación",
                )
                return False, "El jugador cambió de club. La solicitud fue rechazada y el dinero devuelto."

            already = conn.execute(
                """
                SELECT id FROM clause_requests
                WHERE cycle_id = ? AND player_id = ?
                  AND status = 'APROBADO' AND id != ?
                LIMIT 1
                """,
                (fresh["cycle_id"], fresh["player_id"], fresh["id"]),
            ).fetchone()
            if already:
                conn.rollback()
                clausulas.reject_request(
                    fresh,
                    staff_id,
                    "El jugador ya recibió un clausulazo en este mercado",
                )
                return False, "Ese jugador ya fue clausulado en esta ventana. Se devolvió el dinero."

            # El vendedor cobra la cláusula al aprobarse.
            conn.execute(
                "INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)",
                (fresh["seller_club"],),
            )
            conn.execute(
                """
                UPDATE club_finances
                SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP
                WHERE club = ? COLLATE NOCASE
                """,
                (fresh["amount"], fresh["seller_club"]),
            )

            # La operación es definitiva: desaparecen publicaciones/ofertas viejas.
            conn.execute(
                "UPDATE publications SET active = 0 WHERE player = ? COLLATE NOCASE AND active = 1",
                (fresh["player"],),
            )
            conn.execute(
                "UPDATE offers SET status = 'CANCELADA' WHERE player = ? COLLATE NOCASE AND status = 'PENDIENTE'",
                (fresh["player"],),
            )

            notes = (
                f"CLAUSULAZO aprobado por Staff. Cláusula universal {clausulas.fmt_money(fresh['amount'])}. "
                f"Solicitado por {fresh['buyer_username']} ({fresh['buyer_club']}). Sin negociación."
            )
            cur = conn.execute(
                """
                INSERT INTO transfers
                (player, seller, buyer, amount, offer_id, player_id, operation_type,
                 season_id, status, approved_by, approved_at, applied_by, applied_at, notes)
                VALUES (?, ?, ?, ?, 0, ?, 'CLAUSULAZO', ?, 'APLICADA', ?, CURRENT_TIMESTAMP,
                        ?, CURRENT_TIMESTAMP, ?)
                """,
                (
                    fresh["player"],
                    fresh["seller_club"],
                    fresh["buyer_club"],
                    runtime.money(str(fresh["amount"])),
                    fresh["player_id"],
                    fresh["season_id"],
                    staff_id,
                    staff_id,
                    notes,
                ),
            )
            transfer_id = cur.lastrowid

            # CLAVE: al aprobar Staff, el jugador pasa inmediatamente al plantel comprador.
            conn.execute(
                "UPDATE roster_players SET club = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (fresh["buyer_club"], fresh["player_id"]),
            )
            conn.execute(
                """
                INSERT INTO player_history
                (player_id, player, from_club, to_club, transfer_id, season_id, event_type)
                VALUES (?, ?, ?, ?, ?, ?, 'CLAUSULAZO')
                """,
                (
                    fresh["player_id"],
                    fresh["player"],
                    fresh["seller_club"],
                    fresh["buyer_club"],
                    transfer_id,
                    fresh["season_id"],
                ),
            )
            conn.execute(
                """
                UPDATE clause_requests
                SET status = 'APROBADO', transfer_id = ?, decided_by = ?, decided_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (transfer_id, staff_id, fresh["id"]),
            )

            conn.commit()
            return True, transfer_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return approve_request


def apply_clausulazo_safety_patch(runtime):
    # Reemplaza la aprobación original: Staff aprobado = transferencia aplicada al plantel.
    clausulas.approve_request = _build_atomic_approve(runtime)

    # Repara automáticamente clausulazos aprobados antes de este fix (ej. el test actual).
    repaired = _reconcile_approved_clauses(runtime)

    base_view = runtime.OperacionAdminView

    class ClausulazoSafeOperacionAdminView(base_view):
        def __init__(self, operacion_id: int):
            super().__init__(operacion_id)
            op = runtime.operacion_por_id(operacion_id)
            if not op or (op["operation_type"] or "").strip().upper() != "CLAUSULAZO":
                return

            # Un clausulazo aprobado por Staff ya queda aplicado dentro del bot.
            for item in self.children:
                label = getattr(item, "label", None)
                if label in {"Aprobar", "Rechazar admin", "Aplicado en PES"}:
                    item.disabled = True

    ClausulazoSafeOperacionAdminView.__name__ = "OperacionAdminView"
    runtime.OperacionAdminView = ClausulazoSafeOperacionAdminView
    print(
        "AJAP clausulazo safety activo: aprobación Staff mueve plantilla automáticamente"
        + (f" • reparados {repaired} clausulazo(s) previos" if repaired else "")
    )
