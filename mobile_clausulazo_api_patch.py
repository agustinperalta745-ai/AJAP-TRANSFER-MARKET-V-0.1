"""Authenticated AJPA Mobile clausulazo API.

This patch exposes the same clausulazo request flow used by Discord while keeping
all market protections server-side: active market window, universal clause
price, available balance, 20/32 squad limits, one clausulazo per DT/window,
one loss per seller club/window, one clausulazo per player/window and pending
transfer guards. Staff continues to approve/reject the request from Discord.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_read_api
import mobile_write_api as writes

DEFAULT_CLAUSE_PRICE = 50_000_000
FREE_AGENT_CLUB = "Jugador Libre"


class ClauseFailure(writes.ApiFailure):
    pass


def _ensure_schema(conn: sqlite3.Connection) -> None:
    writes.ensure_schema(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            clause_price INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS club_finances (
            club TEXT PRIMARY KEY COLLATE NOCASE,
            balance INTEGER NOT NULL DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS clause_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id INTEGER NOT NULL,
            season_id INTEGER,
            player_id INTEGER NOT NULL,
            player TEXT NOT NULL,
            seller_club TEXT NOT NULL,
            seller_user_id INTEGER,
            buyer_club TEXT NOT NULL,
            buyer_user_id INTEGER NOT NULL,
            buyer_username TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDIENTE_STAFF',
            transfer_id INTEGER,
            requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            decided_by INTEGER,
            decided_at DATETIME,
            notes TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_clause_cycle_player
            ON clause_requests (cycle_id, player_id);
        CREATE INDEX IF NOT EXISTS idx_clause_status
            ON clause_requests (status);
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO market_config(id, clause_price) VALUES(1, ?)",
        (DEFAULT_CLAUSE_PRICE,),
    )


def _cycle(conn: sqlite3.Connection):
    if not writes._table_exists(conn, "market_cycles"):
        return None
    return conn.execute(
        "SELECT * FROM market_cycles WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()


def _clause_price(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT clause_price FROM market_config WHERE id=1").fetchone()
    return int(row["clause_price"]) if row else DEFAULT_CLAUSE_PRICE


def _balance(conn: sqlite3.Connection, club: str) -> int:
    conn.execute("INSERT OR IGNORE INTO club_finances(club,balance) VALUES(?,0)", (club,))
    row = conn.execute(
        "SELECT balance FROM club_finances WHERE club=? COLLATE NOCASE", (club,)
    ).fetchone()
    return int(row["balance"] if row else 0)


def _owner_id(conn: sqlite3.Connection, club: str):
    if not writes._table_exists(conn, "clubs"):
        return None
    cols = writes._columns(conn, "clubs")
    if "name" not in cols or "user_id" not in cols:
        return None
    row = conn.execute(
        "SELECT user_id FROM clubs WHERE name=? COLLATE NOCASE LIMIT 1", (club,)
    ).fetchone()
    return int(row["user_id"]) if row and row["user_id"] is not None else None


def _clause_lock(conn: sqlite3.Connection, cycle_id: int, *, player_id=None, club=None, buyer_user_id=None):
    where = ["cycle_id=?", "status IN ('PENDIENTE_STAFF','APROBADO')"]
    params: list[object] = [int(cycle_id)]
    if player_id is not None:
        where.append("player_id=?")
        params.append(int(player_id))
    if club is not None:
        where.append("seller_club=? COLLATE NOCASE")
        params.append(str(club))
    if buyer_user_id is not None:
        where.append("buyer_user_id=?")
        params.append(int(buyer_user_id))
    return conn.execute(
        f"SELECT * FROM clause_requests WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT 1",
        tuple(params),
    ).fetchone()


def _rating(row):
    return int(row["rating"]) if row is not None and "rating" in row.keys() and row["rating"] is not None else None


def _market_value(row):
    if row is None:
        return 0
    if "min_sale_value" in row.keys() and row["min_sale_value"] is not None:
        return int(row["min_sale_value"])
    return 0


def _target_reason(conn: sqlite3.Connection, cycle_id: int, buyer_club: str, player) -> str | None:
    seller = str(player["club"] or "").strip()
    if not seller or seller.casefold() == FREE_AGENT_CLUB.casefold():
        return "El jugador es agente libre."
    if seller.casefold() == buyer_club.casefold():
        return "El jugador ya pertenece a tu club."
    if writes._open_transfer(conn, int(player["id"]), str(player["name"])):
        return "El jugador tiene una operación pendiente."
    if _clause_lock(conn, cycle_id, player_id=int(player["id"])):
        return "El jugador ya tiene un clausulazo pendiente o aprobado en este mercado."
    if _clause_lock(conn, cycle_id, club=seller):
        return f"{seller} ya está protegido por otro clausulazo de esta ventana."
    seller_state = writes._squad_state(conn, seller)
    if seller_state["active"] <= writes.MIN_SQUAD:
        return f"{seller} tiene {seller_state['active']}/{writes.MIN_SQUAD} jugadores y no puede perder otro."
    return None


def clausulazo_payload(conn: sqlite3.Connection, session: dict) -> dict:
    _ensure_schema(conn)
    club = writes._require_club(conn, session)
    cycle = _cycle(conn)
    amount = _clause_price(conn)
    balance = _balance(conn, club)
    buyer_state = writes._squad_state(conn, club)
    buyer_lock = _clause_lock(conn, int(cycle["id"]), buyer_user_id=session["user_id"]) if cycle else None

    global_reason = None
    if not writes._market_open(conn):
        global_reason = "El mercado está cerrado."
    elif not cycle:
        global_reason = "No hay una ventana de mercado activa."
    elif buyer_state["committed"] >= writes.MAX_SQUAD:
        global_reason = f"{club} ya tiene {buyer_state['committed']}/{writes.MAX_SQUAD} plazas comprometidas."
    elif buyer_lock:
        global_reason = (
            f"Ya usaste tu clausulazo de este mercado por {buyer_lock['player']}."
            if str(buyer_lock["status"]).upper() == "APROBADO"
            else f"Ya tenés un clausulazo pendiente por {buyer_lock['player']}."
        )
    elif balance < amount:
        global_reason = f"Saldo insuficiente: necesitás {writes._money(amount)} y tenés {writes._money(balance)}."

    players = []
    if writes._table_exists(conn, "roster_players"):
        rows = conn.execute(
            """SELECT * FROM roster_players
               WHERE club<>? COLLATE NOCASE AND club<>? COLLATE NOCASE
               ORDER BY name COLLATE NOCASE""",
            (club, FREE_AGENT_CLUB),
        ).fetchall()
        for row in rows:
            reason = global_reason or (_target_reason(conn, int(cycle["id"]), club, row) if cycle else global_reason)
            players.append({
                "id": int(row["id"]),
                "name": str(row["name"]),
                "position": str(row["position"] or "—"),
                "club": str(row["club"]),
                "rating": _rating(row),
                "market_value": _market_value(row),
                "clause": amount,
                "available": reason is None,
                "blocked_reason": reason,
            })

    return {
        "club": club,
        "balance": balance,
        "roster_count": buyer_state["active"],
        "committed_roster": buyer_state["committed"],
        "market_open": writes._market_open(conn),
        "cycle_id": int(cycle["id"]) if cycle else None,
        "clause": amount,
        "available": global_reason is None,
        "blocked_reason": global_reason,
        "players": players,
    }


def create_clause_request(conn: sqlite3.Connection, session: dict, payload: dict) -> dict:
    _ensure_schema(conn)
    buyer = writes._require_club(conn, session)
    if not writes._market_open(conn):
        raise ClauseFailure("El mercado está cerrado.", HTTPStatus.CONFLICT)
    cycle = _cycle(conn)
    if not cycle:
        raise ClauseFailure("No hay una ventana de mercado activa.", HTTPStatus.CONFLICT)

    raw_id = payload.get("player_id")
    if not str(raw_id or "").isdigit():
        raise ClauseFailure("Elegí un jugador válido.")
    player_id = int(raw_id)

    conn.execute("BEGIN IMMEDIATE")
    player = writes._player(conn, player_id)
    if not player:
        raise ClauseFailure("El jugador ya no existe.", HTTPStatus.NOT_FOUND)
    seller = str(player["club"] or "").strip()
    if not seller or seller.casefold() == FREE_AGENT_CLUB.casefold():
        raise ClauseFailure("Ese jugador es agente libre; fichalo desde Agentes Libres.")
    if seller.casefold() == buyer.casefold():
        raise ClauseFailure("No podés ejecutar la cláusula de un jugador de tu propio club.")

    buyer_state = writes._squad_state(conn, buyer)
    if buyer_state["committed"] >= writes.MAX_SQUAD:
        raise ClauseFailure(
            f"{buyer} ya tiene {buyer_state['committed']}/{writes.MAX_SQUAD} plazas comprometidas."
        )
    seller_state = writes._squad_state(conn, seller)
    if seller_state["active"] <= writes.MIN_SQUAD:
        raise ClauseFailure(
            f"{seller} tiene {seller_state['active']}/{writes.MIN_SQUAD} jugadores y no puede perder otro."
        )
    if writes._open_transfer(conn, player_id, str(player["name"])):
        raise ClauseFailure("Ese jugador ya tiene una operación aceptada pendiente de administración.")

    buyer_lock = _clause_lock(conn, int(cycle["id"]), buyer_user_id=session["user_id"])
    if buyer_lock:
        if str(buyer_lock["status"]).upper() == "APROBADO":
            raise ClauseFailure(
                f"Ya usaste tu clausulazo de este mercado por {buyer_lock['player']}.", HTTPStatus.CONFLICT
            )
        raise ClauseFailure(
            f"Ya tenés un clausulazo pendiente por {buyer_lock['player']}.", HTTPStatus.CONFLICT
        )
    player_lock = _clause_lock(conn, int(cycle["id"]), player_id=player_id)
    if player_lock:
        raise ClauseFailure("Ese jugador ya tiene un clausulazo pendiente o aprobado en este mercado.", HTTPStatus.CONFLICT)
    club_lock = _clause_lock(conn, int(cycle["id"]), club=seller)
    if club_lock:
        raise ClauseFailure(
            f"{seller} ya tiene un clausulazo pendiente o aprobado y está protegido en esta ventana.",
            HTTPStatus.CONFLICT,
        )

    amount = _clause_price(conn)
    balance = _balance(conn, buyer)
    if balance < amount:
        raise ClauseFailure(
            f"Saldo insuficiente. Necesitás {writes._money(amount)} y tenés {writes._money(balance)}."
        )

    season_id = writes._active_season_id(conn)
    seller_user_id = _owner_id(conn, seller)
    conn.execute(
        "UPDATE club_finances SET balance=balance-?, updated_at=CURRENT_TIMESTAMP WHERE club=? COLLATE NOCASE",
        (amount, buyer),
    )
    cur = conn.execute(
        """INSERT INTO clause_requests
           (cycle_id,season_id,player_id,player,seller_club,seller_user_id,
            buyer_club,buyer_user_id,buyer_username,amount,status,notes)
           VALUES(?,?,?,?,?,?,?,?,?,?,'PENDIENTE_STAFF',?)""",
        (
            int(cycle["id"]), season_id, player_id, str(player["name"]), seller,
            seller_user_id, buyer, int(session["user_id"]),
            f"AJPA Mobile · {session['user_id']}", amount,
            "Solicitud creada desde AJPA Mobile; requiere aprobación Staff.",
        ),
    )
    after = balance - amount
    return {
        "ok": True,
        "request_id": int(cur.lastrowid),
        "status": "PENDIENTE_STAFF",
        "player": str(player["name"]),
        "seller_club": seller,
        "buyer_club": buyer,
        "amount": amount,
        "balance_after": after,
        "message": "Clausulazo enviado a revisión del Staff. El importe quedó reservado.",
    }


def apply_mobile_clausulazo_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_clausulazo_patch", False):
        return

    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/clausulazo":
            return original_get(self)
        try:
            with writes.write_db() as conn:
                session = writes._session(self.headers, conn)
                self._json(clausulazo_payload(conn, session))
        except writes.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            print(f"AJPA mobile clausulazo GET error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo cargar Clausulazo."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/clausulazo":
            return original_post(self)
        conn = None
        try:
            payload = writes._read_json(self)
            conn = writes.write_db()
            session = writes._session(self.headers, conn)
            result = create_clause_request(conn, session, payload)
            conn.commit()
            self._json(result, HTTPStatus.CREATED)
        except writes.ApiFailure as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._json({"error": "request", "message": exc.message}, exc.status)
        except sqlite3.IntegrityError as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"AJPA mobile clausulazo integrity error: {exc}")
            self._json({"error": "conflict", "message": "La situación cambió. Actualizá e intentá de nuevo."}, HTTPStatus.CONFLICT)
        except Exception as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"AJPA mobile clausulazo POST error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo ejecutar el clausulazo."}, HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            if conn is not None:
                conn.close()

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_clausulazo_patch = True
