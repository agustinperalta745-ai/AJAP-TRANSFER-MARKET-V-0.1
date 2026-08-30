"""Authenticated write API for AJPA Mobile.

The APK uses a one-time pairing code generated inside Discord. After pairing,
the device receives a revocable random session token. Every market mutation is
performed against the same guild-isolated SQLite database used by the bot.

This module intentionally mirrors the bot's core market invariants: ownership,
market open/closed state, one active publication per player, 20/32 squad limits,
minimum AJPA value protection, pending-operation guards, atomic free-agent
reservation, and Staff/PES pending transfers.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import string
import time
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_auth
import mobile_read_api

FREE_AGENT_CLUB = "Jugador Libre"
MIN_SQUAD = 20
MAX_SQUAD = 32
SESSION_TTL = 60 * 60 * 24 * 30
PAIR_TTL = 60 * 10
ACTIVE_LOAN_STATUSES = ("ACTIVE", "OPTION_PENDING", "RETURN_PENDING", "REVIEW_REQUIRED")
PENDING_TRANSFER_STATUSES = ("PENDIENTE_ADMIN", "APROBADA")


class ApiFailure(Exception):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.message = message
        self.status = status


def write_db() -> sqlite3.Connection:
    path = mobile_read_api.configured_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone())


def _columns(conn, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _add_column(conn, table: str, column: str, definition: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mobile_pair_codes (
            code TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            is_staff INTEGER NOT NULL DEFAULT 0,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mobile_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            is_staff INTEGER NOT NULL DEFAULT 0,
            expires_at INTEGER NOT NULL,
            revoked_at INTEGER,
            created_at INTEGER NOT NULL
        );
        """
    )
    if _table_exists(conn, "offers"):
        _add_column(conn, "offers", "offer_kind", "TEXT NOT NULL DEFAULT 'DINERO'")
        _add_column(conn, "offers", "offered_player_id", "INTEGER")
        _add_column(conn, "offers", "offered_player", "TEXT")
    if _table_exists(conn, "transfers"):
        _add_column(conn, "transfers", "deal_group", "TEXT")
    if _table_exists(conn, "publications"):
        _add_column(conn, "publications", "operation_type", "TEXT NOT NULL DEFAULT 'TRANSFERENCIA'")
        _add_column(conn, "publications", "season_id", "INTEGER")
        _add_column(conn, "publications", "loan_seasons", "INTEGER")
        _add_column(conn, "publications", "purchase_option_enabled", "INTEGER")
        _add_column(conn, "publications", "purchase_option_value", "TEXT")


def issue_pair_code(connection_factory, user_id: int, is_staff: bool = False) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    now = int(time.time())
    with connection_factory() as conn:
        ensure_schema(conn)
        conn.execute("DELETE FROM mobile_pair_codes WHERE user_id=? OR expires_at<?", (int(user_id), now))
        for _ in range(20):
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            try:
                conn.execute(
                    "INSERT INTO mobile_pair_codes(code,user_id,is_staff,expires_at,created_at) VALUES(?,?,?,?,?)",
                    (code, int(user_id), 1 if is_staff else 0, now + PAIR_TTL, now),
                )
                return code
            except sqlite3.IntegrityError:
                continue
    raise RuntimeError("No se pudo generar un código de vinculación")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def exchange_pair_code(code: str) -> dict:
    normalized = str(code or "").strip().upper().replace("-", "")
    if len(normalized) != 8:
        raise ApiFailure("El código de vinculación debe tener 8 caracteres.")
    now = int(time.time())
    conn = write_db()
    try:
        ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM mobile_pair_codes WHERE code=? LIMIT 1", (normalized,)
        ).fetchone()
        if not row or row["used_at"] is not None or int(row["expires_at"]) < now:
            conn.rollback()
            raise ApiFailure("El código no existe, venció o ya fue usado.", HTTPStatus.UNAUTHORIZED)
        token = secrets.token_urlsafe(32)
        conn.execute("UPDATE mobile_pair_codes SET used_at=? WHERE code=?", (now, normalized))
        conn.execute(
            "INSERT INTO mobile_sessions(token_hash,user_id,is_staff,expires_at,created_at) VALUES(?,?,?,?,?)",
            (_hash_token(token), int(row["user_id"]), int(row["is_staff"]), now + SESSION_TTL, now),
        )
        conn.commit()
        profile = _profile_from_session(conn, int(row["user_id"]), bool(row["is_staff"]))
        return {"token": token, "profile": profile}
    finally:
        conn.close()


def _bearer(headers) -> str:
    raw = str(headers.get("Authorization") or "").strip()
    if not raw.lower().startswith("bearer "):
        raise ApiFailure("Vinculá la app con Discord para continuar.", HTTPStatus.UNAUTHORIZED)
    token = raw[7:].strip()
    if not token:
        raise ApiFailure("Sesión inválida.", HTTPStatus.UNAUTHORIZED)
    return token


def _session(headers, conn: sqlite3.Connection) -> dict:
    ensure_schema(conn)
    now = int(time.time())
    token = _bearer(headers)
    row = conn.execute(
        "SELECT * FROM mobile_sessions WHERE token_hash=? AND revoked_at IS NULL AND expires_at>? LIMIT 1",
        (_hash_token(token), now),
    ).fetchone()
    if not row:
        raise ApiFailure("La sesión venció. Volvé a vincular la app.", HTTPStatus.UNAUTHORIZED)
    return {"user_id": int(row["user_id"]), "is_staff": bool(row["is_staff"])}


def _profile_from_session(conn, user_id: int, is_staff: bool) -> dict:
    club = mobile_auth.resolve_club_readonly(conn, int(user_id))
    balance = None
    roster_count = 0
    if club and _table_exists(conn, "club_finances"):
        row = conn.execute("SELECT balance FROM club_finances WHERE club=? COLLATE NOCASE", (club,)).fetchone()
        balance = int(row["balance"]) if row else 0
    if club and _table_exists(conn, "roster_players"):
        roster_count = int(conn.execute(
            "SELECT COUNT(*) AS n FROM roster_players WHERE club=? COLLATE NOCASE", (club,)
        ).fetchone()["n"])
    return {
        "authenticated": True,
        "read_only": False,
        "user": {"id": str(user_id)},
        "in_guild": True,
        "is_staff": bool(is_staff),
        "club": club,
        "balance": balance,
        "roster_count": roster_count,
    }


def _require_club(conn, session: dict) -> str:
    club = mobile_auth.resolve_club_readonly(conn, session["user_id"])
    if not club:
        raise ApiFailure("Tu cuenta no tiene un club asignado en AJPA.", HTTPStatus.FORBIDDEN)
    return club


def _market_open(conn) -> bool:
    if not _table_exists(conn, "market_state"):
        return False
    row = conn.execute("SELECT is_open FROM market_state WHERE id=1").fetchone()
    return bool(row and row["is_open"])


def _active_season_id(conn):
    if not _table_exists(conn, "seasons"):
        return None
    row = conn.execute("SELECT id FROM seasons WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _money(value: int) -> str:
    return f"${int(value):,}".replace(",", ".")


def _price_number(value) -> int | None:
    if isinstance(value, int):
        return value
    raw = str(value or "").strip().replace("$", "").replace(".", "").replace(",", "")
    return int(raw) if raw.isdigit() else None


def _normalize_operation(value: str) -> str:
    raw = str(value or "TRANSFERENCIA").strip().upper()
    return {
        "VENTA": "TRANSFERENCIA",
        "TRANSFERENCIA DEFINITIVA": "TRANSFERENCIA",
        "PRESTAMO": "PRÉSTAMO",
        "CESION": "PRÉSTAMO",
        "CESIÓN": "PRÉSTAMO",
        "INTERCAMBIO": "INTERCAMBIO",
    }.get(raw, raw)


def _player(conn, player_id: int):
    return conn.execute("SELECT * FROM roster_players WHERE id=? LIMIT 1", (int(player_id),)).fetchone()


def _active_publication(conn, player_name: str):
    return conn.execute(
        "SELECT * FROM publications WHERE player=? COLLATE NOCASE AND active=1 ORDER BY id DESC LIMIT 1",
        (player_name,),
    ).fetchone()


def _open_transfer(conn, player_id: int, player_name: str):
    return conn.execute(
        """SELECT * FROM transfers WHERE (player_id=? OR player=? COLLATE NOCASE)
           AND status IN ('PENDIENTE_ADMIN','APROBADA') ORDER BY id DESC LIMIT 1""",
        (int(player_id), player_name),
    ).fetchone()


def _active_count(conn, club: str) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) AS n FROM roster_players WHERE club=? COLLATE NOCASE", (club,)
    ).fetchone()["n"])


def _loaned_out_count(conn, club: str) -> int:
    count = 0
    if _table_exists(conn, "loans"):
        marks = ",".join("?" for _ in ACTIVE_LOAN_STATUSES)
        row = conn.execute(
            f"SELECT COUNT(DISTINCT player_id) AS n FROM loans WHERE owner_club=? COLLATE NOCASE AND borrower_club<>owner_club COLLATE NOCASE AND status IN ({marks})",
            (club, *ACTIVE_LOAN_STATUSES),
        ).fetchone()
        count = int(row["n"] if row else 0)
    return count


def _squad_state(conn, club: str) -> dict:
    active = _active_count(conn, club)
    loaned = _loaned_out_count(conn, club)
    return {"active": active, "loaned": loaned, "committed": active + loaned}


def _player_floor(player) -> int:
    if player and "min_sale_value" in player.keys() and player["min_sale_value"] is not None:
        return int(player["min_sale_value"])
    return 0


def _validate_offer_rosters(conn, seller: str, buyer: str, operation: str, offered) -> None:
    ss, bs = _squad_state(conn, seller), _squad_state(conn, buyer)
    op = _normalize_operation(operation)
    if op == "PRÉSTAMO":
        if ss["active"] <= MIN_SQUAD:
            raise ApiFailure(f"{seller} tiene {ss['active']}/{MIN_SQUAD}; no puede ceder jugadores a préstamo.")
        if bs["committed"] >= MAX_SQUAD:
            raise ApiFailure(f"{buyer} ya tiene {bs['committed']}/{MAX_SQUAD} plazas comprometidas.")
        return
    swap = 1 if offered else 0
    if bs["committed"] + 1 - swap > MAX_SQUAD:
        raise ApiFailure(f"La operación dejaría a {buyer} por encima del máximo de {MAX_SQUAD} jugadores.")
    if ss["active"] - 1 + swap < MIN_SQUAD:
        raise ApiFailure(f"La operación dejaría a {seller} por debajo del mínimo de {MIN_SQUAD} jugadores.")
    if offered and bs["active"] + 1 - swap < MIN_SQUAD:
        raise ApiFailure(f"El intercambio dejaría a {buyer} por debajo del mínimo de {MIN_SQUAD} jugadores.")


def _publication_item(conn, pub_id: int) -> dict:
    row = conn.execute("SELECT * FROM publications WHERE id=?", (int(pub_id),)).fetchone()
    return {"publication_id": int(row["id"]), "player": row["player"], "club": row["club"], "price": row["price"], "operation_type": row["operation_type"]} if row else {}


def create_publication(conn, session: dict, payload: dict) -> dict:
    club = _require_club(conn, session)
    player_id = payload.get("player_id")
    if not str(player_id or "").isdigit():
        raise ApiFailure("Elegí un jugador válido de tu plantel.")
    player = _player(conn, int(player_id))
    if not player or str(player["club"]).casefold() != club.casefold():
        raise ApiFailure("Ese jugador ya no pertenece a tu club.", HTTPStatus.FORBIDDEN)
    if _active_publication(conn, player["name"]):
        raise ApiFailure(f"{player['name']} ya tiene una publicación activa.")
    if _open_transfer(conn, int(player["id"]), player["name"]):
        raise ApiFailure(f"{player['name']} ya tiene una operación pendiente de Staff/PES.")

    operation = _normalize_operation(payload.get("operation_type"))
    if operation not in {"TRANSFERENCIA", "PRÉSTAMO", "INTERCAMBIO"}:
        raise ApiFailure("Tipo de publicación inválido.")
    state = _squad_state(conn, club)
    if operation == "PRÉSTAMO" and state["active"] <= MIN_SQUAD:
        raise ApiFailure(f"Con {state['active']} jugadores no podés ceder a préstamo; el mínimo es {MIN_SQUAD}.")
    if operation == "TRANSFERENCIA" and state["active"] <= MIN_SQUAD:
        raise ApiFailure(f"Con {state['active']} jugadores no podés vender; el mínimo es {MIN_SQUAD}. Un intercambio 1x1 sí está permitido.")

    raw_price = _price_number(payload.get("price"))
    if raw_price is None or raw_price < 0:
        raise ApiFailure("El precio debe ser un número igual o mayor a 0.")
    minimum = _player_floor(player)
    if operation == "TRANSFERENCIA" and minimum and raw_price < minimum:
        raise ApiFailure(f"El mínimo AJPA de {player['name']} es {_money(minimum)}.")

    detail = str(payload.get("detail") or "Sin observaciones").strip()[:180] or "Sin observaciones"
    loan_seasons = None
    purchase_enabled = None
    purchase_value = None
    if operation == "PRÉSTAMO":
        seasons = payload.get("loan_seasons")
        if not str(seasons or "").isdigit() or int(seasons) <= 0:
            raise ApiFailure("Indicá cuántas temporadas dura el préstamo.")
        loan_seasons = int(seasons)
        purchase_enabled = 1 if bool(payload.get("purchase_option_enabled")) else 0
        if purchase_enabled:
            purchase_number = _price_number(payload.get("purchase_option_value"))
            if purchase_number is None or purchase_number <= 0:
                raise ApiFailure("Indicá un valor válido para la opción de compra.")
            purchase_value = _money(purchase_number)

    cur = conn.execute(
        """INSERT INTO publications
           (player,position,club,price,detail,owner_id,operation_type,season_id,loan_seasons,purchase_option_enabled,purchase_option_value)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (player["name"], player["position"], club, _money(raw_price), detail,
         session["user_id"], operation, _active_season_id(conn), loan_seasons,
         purchase_enabled, purchase_value),
    )
    return _publication_item(conn, int(cur.lastrowid))


def withdraw_publication(conn, session: dict, pub_id: int) -> dict:
    pub = conn.execute("SELECT * FROM publications WHERE id=? AND active=1", (int(pub_id),)).fetchone()
    if not pub:
        raise ApiFailure("La publicación ya no está activa.", HTTPStatus.NOT_FOUND)
    if int(pub["owner_id"]) != int(session["user_id"]):
        raise ApiFailure("Solo el dueño puede retirar esta publicación.", HTTPStatus.FORBIDDEN)
    conn.execute("UPDATE publications SET active=0 WHERE id=?", (int(pub_id),))
    if _table_exists(conn, "offers"):
        conn.execute("UPDATE offers SET status='CANCELADA' WHERE publication_id=? AND status='PENDIENTE'", (int(pub_id),))
    return {"ok": True, "publication_id": int(pub_id)}


def create_offer(conn, session: dict, pub_id: int, payload: dict) -> dict:
    if not _market_open(conn):
        raise ApiFailure("El mercado está cerrado.", HTTPStatus.CONFLICT)
    buyer = _require_club(conn, session)
    pub = conn.execute("SELECT * FROM publications WHERE id=? AND active=1", (int(pub_id),)).fetchone()
    if not pub:
        raise ApiFailure("La publicación ya no está disponible.", HTTPStatus.NOT_FOUND)
    if str(pub["club"]).casefold() == FREE_AGENT_CLUB.casefold():
        raise ApiFailure("Los agentes libres se fichan directamente por $0.")
    if int(pub["owner_id"]) == int(session["user_id"]):
        raise ApiFailure("No podés ofertar por tu propia publicación.")
    if str(pub["club"]).casefold() == buyer.casefold():
        raise ApiFailure("Ese jugador ya pertenece a tu club.")
    target = conn.execute("SELECT * FROM roster_players WHERE name=? COLLATE NOCASE", (pub["player"],)).fetchone()
    if not target or str(target["club"]).casefold() != str(pub["club"]).casefold():
        raise ApiFailure("La propiedad del jugador cambió; la publicación ya no es válida.")
    if _open_transfer(conn, int(target["id"]), target["name"]):
        raise ApiFailure("Ese jugador ya tiene una operación pendiente.")

    cash = _price_number(payload.get("amount") or 0)
    if cash is None or cash < 0:
        raise ApiFailure("El dinero ofrecido debe ser un número.")
    offered = None
    offered_id = payload.get("offered_player_id")
    if offered_id not in (None, ""):
        if not str(offered_id).isdigit():
            raise ApiFailure("Jugador ofrecido inválido.")
        offered = _player(conn, int(offered_id))
        if not offered or str(offered["club"]).casefold() != buyer.casefold():
            raise ApiFailure("El jugador ofrecido no pertenece a tu club.")
        if int(offered["id"]) == int(target["id"]):
            raise ApiFailure("No podés ofrecer el mismo jugador.")
        if _open_transfer(conn, int(offered["id"]), offered["name"]):
            raise ApiFailure(f"{offered['name']} ya tiene una operación pendiente.")
        if _normalize_operation(pub["operation_type"]) == "PRÉSTAMO":
            raise ApiFailure("En préstamos, por ahora la propuesta desde la app debe ser económica.")
    if cash <= 0 and not offered:
        raise ApiFailure("La oferta debe incluir dinero, un jugador o ambos.")

    target_floor = _player_floor(target)
    offered_floor = _player_floor(offered)
    total = cash + offered_floor
    if target_floor and total < target_floor:
        raise ApiFailure(f"La propuesta vale {_money(total)} y debe alcanzar al menos {_money(target_floor)}.")

    _validate_offer_rosters(conn, str(pub["club"]), buyer, str(pub["operation_type"]), offered)
    kind = "JUGADOR + DINERO" if offered and cash > 0 else "INTERCAMBIO" if offered else "DINERO"
    message = str(payload.get("message") or "Sin condiciones adicionales").strip()[:180] or "Sin condiciones adicionales"
    cur = conn.execute(
        """INSERT INTO offers
           (publication_id,player,amount,message,from_id,from_club,to_id,to_club,operation_type,season_id,offer_kind,offered_player_id,offered_player)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (int(pub["id"]), pub["player"], _money(cash), message, session["user_id"], buyer,
         int(pub["owner_id"]), pub["club"], pub["operation_type"], pub["season_id"], kind,
         int(offered["id"]) if offered else None, offered["name"] if offered else None),
    )
    return {"ok": True, "offer_id": int(cur.lastrowid), "offer_kind": kind}


def offers_payload(conn, session: dict) -> dict:
    uid = int(session["user_id"])
    if not _table_exists(conn, "offers"):
        return {"incoming": [], "outgoing": []}
    rows = conn.execute(
        "SELECT * FROM offers WHERE from_id=? OR to_id=? ORDER BY id DESC LIMIT 100", (uid, uid)
    ).fetchall()
    def item(row):
        keys = set(row.keys())
        return {
            "id": int(row["id"]), "publication_id": int(row["publication_id"]), "player": row["player"],
            "amount": row["amount"], "message": row["message"], "from_club": row["from_club"],
            "to_club": row["to_club"], "status": row["status"],
            "operation_type": row["operation_type"] if "operation_type" in keys else "TRANSFERENCIA",
            "offer_kind": row["offer_kind"] if "offer_kind" in keys else "DINERO",
            "offered_player_id": row["offered_player_id"] if "offered_player_id" in keys else None,
            "offered_player": row["offered_player"] if "offered_player" in keys else None,
            "incoming": int(row["to_id"]) == uid,
        }
    incoming, outgoing = [], []
    for row in rows:
        target = incoming if int(row["to_id"]) == uid else outgoing
        target.append(item(row))
    return {"incoming": incoming, "outgoing": outgoing}


def decide_offer(conn, session: dict, offer_id: int, accept: bool) -> dict:
    if not _market_open(conn):
        raise ApiFailure("El mercado está cerrado; las ofertas quedan congeladas.", HTTPStatus.CONFLICT)
    offer = conn.execute("SELECT * FROM offers WHERE id=?", (int(offer_id),)).fetchone()
    if not offer or int(offer["to_id"]) != int(session["user_id"]):
        raise ApiFailure("No podés gestionar esta oferta.", HTTPStatus.FORBIDDEN)
    if str(offer["status"]) != "PENDIENTE":
        raise ApiFailure("La oferta ya fue resuelta.", HTTPStatus.CONFLICT)
    if not accept:
        conn.execute("UPDATE offers SET status='RECHAZADA' WHERE id=?", (int(offer_id),))
        return {"ok": True, "offer_id": int(offer_id), "status": "RECHAZADA"}

    pub = conn.execute("SELECT * FROM publications WHERE id=? AND active=1", (int(offer["publication_id"]),)).fetchone()
    target = conn.execute("SELECT * FROM roster_players WHERE name=? COLLATE NOCASE", (offer["player"],)).fetchone()
    if not pub or not target or str(target["club"]).casefold() != str(offer["to_club"]).casefold():
        conn.execute("UPDATE offers SET status='CANCELADA' WHERE id=?", (int(offer_id),))
        raise ApiFailure("La publicación o propiedad cambió; la oferta fue cancelada.", HTTPStatus.CONFLICT)
    if _open_transfer(conn, int(target["id"]), target["name"]):
        raise ApiFailure("El jugador ya tiene otra operación pendiente.")

    offered = None
    keys = set(offer.keys())
    offered_id = offer["offered_player_id"] if "offered_player_id" in keys else None
    if offered_id:
        offered = _player(conn, int(offered_id))
        if not offered or str(offered["club"]).casefold() != str(offer["from_club"]).casefold():
            raise ApiFailure("El jugador ofrecido ya no pertenece al club comprador.")
        if _open_transfer(conn, int(offered["id"]), offered["name"]):
            raise ApiFailure(f"{offered['name']} ya tiene otra operación pendiente.")

    _validate_offer_rosters(conn, str(offer["to_club"]), str(offer["from_club"]), str(offer["operation_type"]), offered)
    kind = str(offer["offer_kind"] if "offer_kind" in keys else "DINERO")
    group = f"OFERTA-{int(offer['id'])}"
    conn.execute("UPDATE offers SET status='ACEPTADA' WHERE id=?", (int(offer_id),))
    conn.execute("UPDATE publications SET active=0 WHERE id=?", (int(pub["id"]),))
    conn.execute("UPDATE offers SET status='RECHAZADA' WHERE publication_id=? AND id<>? AND status='PENDIENTE'", (int(pub["id"]), int(offer_id)))
    if offered:
        conn.execute("UPDATE publications SET active=0 WHERE player=? COLLATE NOCASE AND active=1", (offered["name"],))
        conn.execute("UPDATE offers SET status='CANCELADA' WHERE player=? COLLATE NOCASE AND status='PENDIENTE'", (offered["name"],))

    op_type = _normalize_operation(offer["operation_type"])
    primary_type = op_type if op_type == "PRÉSTAMO" else ("TRANSFERENCIA" if kind == "DINERO" else kind)
    notes = str(offer["message"] or "Sin condiciones adicionales")
    cur = conn.execute(
        """INSERT INTO transfers(player,seller,buyer,amount,offer_id,player_id,operation_type,season_id,status,notes,deal_group)
           VALUES(?,?,?,?,?,?,?,?, 'PENDIENTE_ADMIN',?,?)""",
        (offer["player"], offer["to_club"], offer["from_club"], offer["amount"], int(offer["id"]),
         int(target["id"]), primary_type, offer["season_id"], notes, group),
    )
    transfer_ids = [int(cur.lastrowid)]
    if offered:
        cur = conn.execute(
            """INSERT INTO transfers(player,seller,buyer,amount,offer_id,player_id,operation_type,season_id,status,notes,deal_group)
               VALUES(?,?,?,'$0',?,?, 'INTERCAMBIO',?, 'PENDIENTE_ADMIN',?,?)""",
            (offered["name"], offer["from_club"], offer["to_club"], int(offer["id"]), int(offered["id"]),
             offer["season_id"], f"Contraparte de {offer['player']} | Oferta #{offer['id']}", group),
        )
        transfer_ids.append(int(cur.lastrowid))
    return {"ok": True, "offer_id": int(offer_id), "status": "ACEPTADA", "transfer_ids": transfer_ids}


def sign_free_agent(conn, session: dict, pub_id: int) -> dict:
    buyer = _require_club(conn, session)
    if not _market_open(conn):
        raise ApiFailure("El mercado está cerrado.", HTTPStatus.CONFLICT)
    state = _squad_state(conn, buyer)
    if state["committed"] >= MAX_SQUAD:
        raise ApiFailure(f"{buyer} ya tiene {state['committed']}/{MAX_SQUAD} plazas comprometidas.")

    conn.execute("BEGIN IMMEDIATE")
    pub = conn.execute("SELECT * FROM publications WHERE id=? AND active=1", (int(pub_id),)).fetchone()
    if not pub or not (str(pub["club"]).casefold() == FREE_AGENT_CLUB.casefold() or _normalize_operation(pub["operation_type"]) == "JUGADOR LIBRE"):
        raise ApiFailure("El agente libre ya no está disponible.", HTTPStatus.CONFLICT)
    player = conn.execute("SELECT * FROM roster_players WHERE name=? COLLATE NOCASE", (pub["player"],)).fetchone()
    if not player or str(player["club"]).casefold() != FREE_AGENT_CLUB.casefold():
        conn.execute("UPDATE publications SET active=0 WHERE id=?", (int(pub_id),))
        raise ApiFailure("El jugador ya no figura como agente libre.", HTTPStatus.CONFLICT)
    if _open_transfer(conn, int(player["id"]), player["name"]):
        conn.execute("UPDATE publications SET active=0 WHERE id=?", (int(pub_id),))
        raise ApiFailure("Otro club ya reservó a este jugador.", HTTPStatus.CONFLICT)
    cur = conn.execute("UPDATE publications SET active=0 WHERE id=? AND active=1", (int(pub_id),))
    if cur.rowcount != 1:
        raise ApiFailure("Otro club se adelantó.", HTTPStatus.CONFLICT)
    cur = conn.execute(
        """INSERT INTO transfers(player,seller,buyer,amount,offer_id,player_id,operation_type,season_id,status,notes)
           VALUES(?,?,?,'$0',0,?, 'JUGADOR LIBRE',?, 'PENDIENTE_ADMIN',?)""",
        (player["name"], FREE_AGENT_CLUB, buyer, int(player["id"]), pub["season_id"], "Fichaje gratuito de agente libre desde AJPA Mobile"),
    )
    return {"ok": True, "transfer_id": int(cur.lastrowid), "player": player["name"], "buyer": buyer}


def release_player(conn, session: dict, player_id: int) -> dict:
    club = _require_club(conn, session)
    if not _market_open(conn):
        raise ApiFailure("Solo podés liberar jugadores con el mercado abierto.", HTTPStatus.CONFLICT)
    player = _player(conn, int(player_id))
    if not player or str(player["club"]).casefold() != club.casefold():
        raise ApiFailure("Ese jugador ya no pertenece a tu club.", HTTPStatus.FORBIDDEN)
    state = _squad_state(conn, club)
    if state["active"] <= MIN_SQUAD:
        raise ApiFailure(f"No podés liberar: {club} tiene {state['active']}/{MIN_SQUAD} jugadores.")
    if _open_transfer(conn, int(player["id"]), player["name"]):
        raise ApiFailure("Ese jugador tiene una operación pendiente.")
    if _table_exists(conn, "loans"):
        marks = ",".join("?" for _ in ACTIVE_LOAN_STATUSES)
        if conn.execute(f"SELECT 1 FROM loans WHERE player_id=? AND status IN ({marks}) LIMIT 1", (int(player["id"]), *ACTIVE_LOAN_STATUSES)).fetchone():
            raise ApiFailure("Ese jugador tiene un préstamo activo.")
    value = _player_floor(player)
    if value <= 0:
        raise ApiFailure("No se pudo determinar el valor AJPA del jugador.")
    cost = int(round(value * 0.20))

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS player_releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL, player TEXT NOT NULL,
            from_club TEXT NOT NULL COLLATE NOCASE, market_value INTEGER NOT NULL, release_percent INTEGER NOT NULL,
            release_cost INTEGER NOT NULL, balance_before INTEGER NOT NULL, balance_after INTEGER NOT NULL,
            released_by INTEGER NOT NULL, season_id INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS club_finances (
            club TEXT PRIMARY KEY COLLATE NOCASE, balance INTEGER NOT NULL DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS treasury_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, club TEXT NOT NULL COLLATE NOCASE, season_id INTEGER,
            direction TEXT NOT NULL, category TEXT NOT NULL, amount INTEGER NOT NULL, player_id INTEGER, player TEXT,
            counterparty TEXT, reference_type TEXT, reference_id INTEGER, description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    row = conn.execute("SELECT balance FROM club_finances WHERE club=? COLLATE NOCASE", (club,)).fetchone()
    balance = int(row["balance"] if row else 0)
    if balance < cost:
        raise ApiFailure(f"Saldo insuficiente: tenés {_money(balance)} y liberar cuesta {_money(cost)}.")
    after = balance - cost
    season_id = _active_season_id(conn)
    conn.execute("UPDATE club_finances SET balance=?, updated_at=CURRENT_TIMESTAMP WHERE club=? COLLATE NOCASE", (after, club))
    cur = conn.execute(
        """INSERT INTO player_releases(player_id,player,from_club,market_value,release_percent,release_cost,balance_before,balance_after,released_by,season_id)
           VALUES(?,?,?,?,20,?,?,?,?,?)""",
        (int(player["id"]), player["name"], club, value, cost, balance, after, session["user_id"], season_id),
    )
    release_id = int(cur.lastrowid)
    conn.execute(
        """INSERT INTO treasury_transactions(club,season_id,direction,category,amount,player_id,player,counterparty,reference_type,reference_id,description)
           VALUES(?,?,'EGRESO','LIBERACIÓN',?,?,?,?, 'PLAYER_RELEASE',?,?)""",
        (club, season_id, cost, int(player["id"]), player["name"], FREE_AGENT_CLUB, release_id, f"Liberación de {player['name']} desde AJPA Mobile"),
    )
    conn.execute("UPDATE roster_players SET club=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (FREE_AGENT_CLUB, int(player["id"])))
    conn.execute("UPDATE publications SET active=0 WHERE player=? COLLATE NOCASE AND active=1", (player["name"],))
    if _table_exists(conn, "offers"):
        conn.execute("UPDATE offers SET status='CANCELADA' WHERE player=? COLLATE NOCASE AND status='PENDIENTE'", (player["name"],))
    if _table_exists(conn, "player_history"):
        conn.execute(
            "INSERT INTO player_history(player_id,player,from_club,to_club,season_id,event_type) VALUES(?,?,?,?,?,'LIBERACIÓN')",
            (int(player["id"]), player["name"], club, FREE_AGENT_CLUB, season_id),
        )
    cur = conn.execute(
        """INSERT INTO publications(player,position,club,price,detail,owner_id,active,operation_type,season_id)
           VALUES(?,?,?,'$0',?,0,1,'JUGADOR LIBRE',?)""",
        (player["name"], player["position"], FREE_AGENT_CLUB,
         f"🆓 Agente libre por liberación • Último club: {club} • Fichaje inmediato por $0", season_id),
    )
    return {"ok": True, "release_id": release_id, "publication_id": int(cur.lastrowid), "cost": cost, "balance_after": after}


def _read_json(handler) -> dict:
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except ValueError:
        length = 0
    if length <= 0:
        return {}
    if length > 64_000:
        raise ApiFailure("Solicitud demasiado grande.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
    try:
        return json.loads(handler.rfile.read(length).decode("utf-8"))
    except Exception as exc:
        raise ApiFailure("JSON inválido.") from exc


def _path_parts(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part]


def apply_mobile_write_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_write_patch", False):
        return

    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/api/v1/me":
                with write_db() as conn:
                    session = _session(self.headers, conn)
                    self._json(_profile_from_session(conn, session["user_id"], session["is_staff"]))
                return
            if path == "/api/v1/my/offers":
                with write_db() as conn:
                    session = _session(self.headers, conn)
                    self._json(offers_payload(conn, session))
                return
        except ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
            return
        return original_get(self)

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        parts = _path_parts(path)
        try:
            payload = _read_json(self)
            if path == "/api/v1/auth/pair":
                self._json(exchange_pair_code(payload.get("code")))
                return
            with write_db() as conn:
                ensure_schema(conn)
                session = _session(self.headers, conn)
                result = None
                if path == "/api/v1/publications":
                    result = create_publication(conn, session, payload)
                elif len(parts) == 5 and parts[:3] == ["api", "v1", "publications"] and parts[4] == "withdraw" and parts[3].isdigit():
                    result = withdraw_publication(conn, session, int(parts[3]))
                elif len(parts) == 5 and parts[:3] == ["api", "v1", "publications"] and parts[4] == "offers" and parts[3].isdigit():
                    result = create_offer(conn, session, int(parts[3]), payload)
                elif len(parts) == 5 and parts[:3] == ["api", "v1", "offers"] and parts[3].isdigit() and parts[4] in {"accept", "reject"}:
                    result = decide_offer(conn, session, int(parts[3]), parts[4] == "accept")
                elif len(parts) == 5 and parts[:3] == ["api", "v1", "free-agents"] and parts[3].isdigit() and parts[4] == "sign":
                    result = sign_free_agent(conn, session, int(parts[3]))
                elif len(parts) == 5 and parts[:3] == ["api", "v1", "players"] and parts[3].isdigit() and parts[4] == "release":
                    result = release_player(conn, session, int(parts[3]))
                else:
                    return original_post(self)
                conn.commit()
                self._json(result, HTTPStatus.CREATED if path == "/api/v1/publications" else HTTPStatus.OK)
                return
        except ApiFailure as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            self._json({"error": "request", "message": exc.message}, exc.status)
        except sqlite3.IntegrityError as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"AJPA mobile write integrity error: {exc}")
            self._json({"error": "conflict", "message": "La operación cambió mientras la procesábamos. Actualizá e intentá de nuevo."}, HTTPStatus.CONFLICT)
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"AJPA mobile write error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo completar la operación."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_write_patch = True
