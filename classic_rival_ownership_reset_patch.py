"""Reset de clásicos + protección ante cambios de DT.

Esta capa hace dos cosas sin tocar resultados de Liga:
1) ejecuta una limpieza global, una sola vez por base, de propuestas/parejas de
   clásico para que todos los DT vuelvan a emparejarse desde cero;
2) invalida automáticamente propuestas o clásicos que pertenecían al dueño
   anterior de un club, evitando que un DT nuevo herede el estado del anterior.
"""

from __future__ import annotations

import sqlite3

import mobile_classic_rival_api_patch as classic
import mobile_write_api


RESET_KEY = "classic-full-reset-2026-09-11-v1"
_RELEASE_REASON = "OWNER_CHANGED_OR_VACANT"
_CANCEL_STATUS = "CANCELLED_OWNER_CHANGED"


_ORIGINAL_ENSURE = classic.ensure_schema
_ORIGINAL_PUBLIC_PAYLOAD = classic.classic_public_payload


def _ensure_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS classic_system_meta (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _run_one_time_reset(conn: sqlite3.Connection) -> bool:
    """Borra sólo el estado de clásicos una vez; nunca toca league_matches."""
    _ensure_meta(conn)
    row = conn.execute(
        "SELECT 1 FROM classic_system_meta WHERE key=? LIMIT 1",
        (RESET_KEY,),
    ).fetchone()
    if row:
        return False

    # Outbox primero para impedir que un clásico viejo se anuncie después del reset.
    conn.execute("DELETE FROM classic_market_outbox")
    conn.execute("DELETE FROM classic_rivals")
    conn.execute("DELETE FROM classic_rival_requests")
    conn.execute(
        "INSERT INTO classic_system_meta (key, value) VALUES (?, ?)",
        (RESET_KEY, "all classic requests/pairs cleared; league history preserved"),
    )
    print("AJPA clásicos: reset global aplicado; todos los DT pueden emparejarse de nuevo")
    return True


def _request_owners_still_match(conn: sqlite3.Connection, row) -> bool:
    requester_owner = classic._owner_id(conn, str(row["requester_club"]))
    target_owner = classic._owner_id(conn, str(row["target_club"]))
    if requester_owner is None or target_owner is None:
        return False
    return (
        int(requester_owner) == int(row["requester_user_id"])
        and int(target_owner) == int(row["target_user_id"])
    )


def _cleanup_stale_ownership(conn: sqlite3.Connection) -> tuple[int, int]:
    """Quita estado heredado cuando cambia o desaparece el dueño de un club."""
    cancelled = 0
    released = 0

    pending = conn.execute(
        """
        SELECT id, requester_club, target_club, requester_user_id, target_user_id
        FROM classic_rival_requests
        WHERE status='PENDING'
        """
    ).fetchall()
    for row in pending:
        if _request_owners_still_match(conn, row):
            continue
        conn.execute(
            """
            UPDATE classic_rival_requests
            SET status=?, responded_at=CURRENT_TIMESTAMP
            WHERE id=? AND status='PENDING'
            """,
            (_CANCEL_STATUS, int(row["id"])),
        )
        cancelled += 1

    active_pairs = conn.execute(
        """
        SELECT id, club_a, club_b, accepted_request_id
        FROM classic_rivals
        WHERE active=1
        """
    ).fetchall()
    for pair in active_pairs:
        owner_a = classic._owner_id(conn, str(pair["club_a"]))
        owner_b = classic._owner_id(conn, str(pair["club_b"]))
        stale = owner_a is None or owner_b is None

        request_id = pair["accepted_request_id"]
        if not stale:
            # Todo clásico creado por la versión actual conserva la solicitud que
            # identifica a los dos DT originales. Si cambia uno, se desactiva.
            if request_id is None:
                stale = True
            else:
                request = conn.execute(
                    """
                    SELECT requester_club, target_club, requester_user_id, target_user_id
                    FROM classic_rival_requests
                    WHERE id=? LIMIT 1
                    """,
                    (int(request_id),),
                ).fetchone()
                stale = request is None or not _request_owners_still_match(conn, request)

        if not stale:
            continue
        conn.execute(
            """
            UPDATE classic_rivals
            SET active=0,
                released_at=CURRENT_TIMESTAMP,
                release_reason=?
            WHERE id=? AND active=1
            """,
            (_RELEASE_REASON, int(pair["id"])),
        )
        conn.execute(
            "DELETE FROM classic_market_outbox WHERE classic_id=?",
            (int(pair["id"]),),
        )
        released += 1

    if cancelled or released:
        print(
            "AJPA clásicos: estado viejo por cambio de DT limpiado | "
            f"solicitudes={cancelled} clásicos={released}"
        )
    return cancelled, released


def _ensure_with_ownership_guard(conn: sqlite3.Connection) -> None:
    # Algunas acciones llaman ensure_schema dentro de BEGIN IMMEDIATE. En ese
    # caso participamos de la transacción sin hacer commit. Fuera de una
    # transacción, persistimos la migración/limpieza antes de devolver el control.
    was_in_transaction = bool(conn.in_transaction)
    _ORIGINAL_ENSURE(conn)
    _run_one_time_reset(conn)
    _cleanup_stale_ownership(conn)
    if not was_in_transaction and conn.in_transaction:
        conn.commit()


def _public_payload_with_guard(conn: sqlite3.Connection, club: str):
    _ensure_with_ownership_guard(conn)
    return _ORIGINAL_PUBLIC_PAYLOAD(conn, club)


def apply_classic_rival_ownership_reset_patch() -> None:
    if getattr(classic, "_ajpa_classic_owner_reset_patch", False):
        return

    # Todas las rutas Mobile y todas las vistas Discord llaman estas funciones;
    # así la regla queda compartida y no depende de qué interfaz use el DT.
    classic.ensure_schema = _ensure_with_ownership_guard
    classic.classic_public_payload = _public_payload_with_guard
    classic._ajpa_classic_owner_reset_patch = True

    # Aplicar ya mismo sobre la DB Mobile configurada. Las DB aisladas por guild
    # reciben exactamente la misma migración la primera vez que abren Clásico.
    try:
        with mobile_write_api.write_db() as conn:
            _ensure_with_ownership_guard(conn)
            conn.commit()
    except Exception as exc:
        print(f"AJPA clásicos reset/ownership warning: {type(exc).__name__}: {exc}")

    print("AJPA clásicos: protección contra herencia de DT + reset one-shot activos")
