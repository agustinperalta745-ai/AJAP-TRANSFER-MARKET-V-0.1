"""Public AJPA Mobile rival-search board backed by official league results.

Every paired club can publish one active PES room. The public list never exposes
room credentials. A rival receives lobby/room/password only after successfully
joining. Joining is blocked when the two clubs already have an official result
in ``league_matches``; that table is written by AJPA's result bot and is the
source of truth for this eligibility rule.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_read_api
import mobile_write_api


OPEN = "OPEN"
MATCHED = "MATCHED"
COMPLETED = "COMPLETED"
CANCELLED = "CANCELLED"


def _norm_team(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    aliases = {
        "sevilla fc": "sevilla",
        "villarreal cf": "villarreal",
        "villareal": "villarreal",
        "villareal cf": "villarreal",
        "paris saint germain psg": "paris saint germain",
        "psg": "paris saint germain",
    }
    return aliases.get(text, text)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mobile_match_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_user_id INTEGER NOT NULL,
            creator_club TEXT NOT NULL,
            pes_lobby TEXT NOT NULL,
            room_name TEXT NOT NULL,
            room_password TEXT,
            status TEXT NOT NULL DEFAULT 'OPEN',
            opponent_user_id INTEGER,
            opponent_club TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            matched_at DATETIME,
            completed_at DATETIME,
            cancelled_at DATETIME
        );
        CREATE INDEX IF NOT EXISTS idx_mobile_match_search_status
            ON mobile_match_searches(status, id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mobile_match_search_open_club
            ON mobile_match_searches(creator_club COLLATE NOCASE)
            WHERE status='OPEN';
        """
    )
    cols = mobile_write_api._columns(conn, "mobile_match_searches")
    if "completed_at" not in cols:
        conn.execute("ALTER TABLE mobile_match_searches ADD COLUMN completed_at DATETIME")


def _already_played(conn: sqlite3.Connection, club_a: str, club_b: str) -> bool:
    if not mobile_write_api._table_exists(conn, "league_matches"):
        return False
    a = _norm_team(club_a)
    b = _norm_team(club_b)
    if not a or not b:
        return False
    rows = conn.execute(
        "SELECT home_team, away_team FROM league_matches ORDER BY id DESC"
    ).fetchall()
    for row in rows:
        home = _norm_team(row["home_team"])
        away = _norm_team(row["away_team"])
        if {home, away} == {a, b}:
            return True
    return False


def _reconcile_completed(conn: sqlite3.Connection) -> None:
    """Close matched searches once the result bot records that exact fixture."""
    rows = conn.execute(
        """
        SELECT id, creator_club, opponent_club
        FROM mobile_match_searches
        WHERE status='MATCHED' AND opponent_club IS NOT NULL
        """
    ).fetchall()
    for row in rows:
        if _already_played(conn, str(row["creator_club"]), str(row["opponent_club"])):
            conn.execute(
                """
                UPDATE mobile_match_searches
                SET status='COMPLETED', completed_at=CURRENT_TIMESTAMP
                WHERE id=? AND status='MATCHED'
                """,
                (int(row["id"]),),
            )


def _active_search_for_club(conn: sqlite3.Connection, club: str):
    return conn.execute(
        """
        SELECT * FROM mobile_match_searches
        WHERE creator_club=? COLLATE NOCASE AND status='OPEN'
        ORDER BY id DESC LIMIT 1
        """,
        (club,),
    ).fetchone()


def _matched_search_for_club(conn: sqlite3.Connection, club: str):
    _reconcile_completed(conn)
    return conn.execute(
        """
        SELECT * FROM mobile_match_searches
        WHERE status='MATCHED'
          AND (creator_club=? COLLATE NOCASE OR opponent_club=? COLLATE NOCASE)
        ORDER BY id DESC LIMIT 1
        """,
        (club, club),
    ).fetchone()


def _eligibility(conn: sqlite3.Connection, viewer_club: str | None, creator_club: str) -> tuple[bool, str | None]:
    if not viewer_club:
        return False, "Vinculá tu cuenta y necesitás un club para aceptar un partido."
    if _norm_team(viewer_club) == _norm_team(creator_club):
        return False, "Es la búsqueda de tu propio club."
    if _already_played(conn, viewer_club, creator_club):
        return False, f"{viewer_club} ya enfrentó a {creator_club} en la liga."
    if _active_search_for_club(conn, viewer_club):
        return False, "Tu club ya está buscando rival. Cancelá esa búsqueda primero."
    if _matched_search_for_club(conn, viewer_club):
        return False, "Tu club ya tiene un rival encontrado."
    return True, None


def _optional_session(headers, conn: sqlite3.Connection):
    if not str(headers.get("Authorization") or "").strip():
        return None
    try:
        return mobile_write_api._session(headers, conn)
    except mobile_write_api.ApiFailure:
        return None


def searches_payload(conn: sqlite3.Connection, session: dict | None) -> dict:
    _ensure_schema(conn)
    _reconcile_completed(conn)
    viewer_club = None
    if session:
        viewer_club = mobile_write_api.mobile_auth.resolve_club_readonly(
            conn, int(session["user_id"])
        )

    rows = conn.execute(
        """
        SELECT * FROM mobile_match_searches
        WHERE status='OPEN'
           OR (status='MATCHED' AND ? IS NOT NULL
               AND (creator_club=? COLLATE NOCASE OR opponent_club=? COLLATE NOCASE))
        ORDER BY CASE status WHEN 'OPEN' THEN 0 ELSE 1 END, id DESC
        LIMIT 100
        """,
        (viewer_club, viewer_club, viewer_club),
    ).fetchall()

    items = []
    for row in rows:
        status = str(row["status"])
        is_owner = bool(viewer_club and _norm_team(viewer_club) == _norm_team(row["creator_club"]))
        is_opponent = bool(viewer_club and row["opponent_club"] and _norm_team(viewer_club) == _norm_team(row["opponent_club"]))
        can_join, reason = (False, None)
        if status == OPEN:
            can_join, reason = _eligibility(conn, viewer_club, str(row["creator_club"]))

        item = {
            "id": int(row["id"]),
            "creator_club": str(row["creator_club"]),
            "status": status,
            "opponent_club": str(row["opponent_club"] or "") or None,
            "created_at": str(row["created_at"] or ""),
            "matched_at": str(row["matched_at"] or "") or None,
            "is_owner": is_owner,
            "is_opponent": is_opponent,
            "can_join": bool(can_join),
            "blocked_reason": reason,
        }
        if is_owner or is_opponent:
            item["room_access"] = {
                "pes_lobby": str(row["pes_lobby"]),
                "room_name": str(row["room_name"]),
                "password": str(row["room_password"] or "") or None,
            }
        items.append(item)

    return {"items": items, "viewer_club": viewer_club}


def create_search(conn: sqlite3.Connection, session: dict, payload: dict) -> dict:
    _ensure_schema(conn)
    _reconcile_completed(conn)
    club = mobile_write_api._require_club(conn, session)
    lobby = str(payload.get("pes_lobby") or "").strip()
    room = str(payload.get("room_name") or "").strip()
    password = str(payload.get("password") or "").strip()
    if not lobby:
        raise mobile_write_api.ApiFailure("Indicá el vestíbulo de PES.")
    if not room:
        raise mobile_write_api.ApiFailure("Indicá el nombre de la sala.")
    if len(lobby) > 80 or len(room) > 80 or len(password) > 80:
        raise mobile_write_api.ApiFailure("Los datos de la sala son demasiado largos.")
    if _active_search_for_club(conn, club):
        raise mobile_write_api.ApiFailure("Tu club ya tiene una búsqueda de rival activa.", HTTPStatus.CONFLICT)
    if _matched_search_for_club(conn, club):
        raise mobile_write_api.ApiFailure("Tu club ya tiene un rival encontrado.", HTTPStatus.CONFLICT)

    cur = conn.execute(
        """
        INSERT INTO mobile_match_searches
            (creator_user_id, creator_club, pes_lobby, room_name, room_password, status)
        VALUES (?, ?, ?, ?, ?, 'OPEN')
        """,
        (int(session["user_id"]), club, lobby, room, password or None),
    )
    return {"ok": True, "id": int(cur.lastrowid), "creator_club": club, "status": OPEN}


def join_search(conn: sqlite3.Connection, session: dict, search_id: int) -> dict:
    _ensure_schema(conn)
    club = mobile_write_api._require_club(conn, session)
    conn.execute("BEGIN IMMEDIATE")
    _reconcile_completed(conn)
    row = conn.execute(
        "SELECT * FROM mobile_match_searches WHERE id=? LIMIT 1",
        (int(search_id),),
    ).fetchone()
    if not row or str(row["status"]) != OPEN:
        raise mobile_write_api.ApiFailure("Esa búsqueda ya no está disponible.", HTTPStatus.CONFLICT)

    creator = str(row["creator_club"])
    can_join, reason = _eligibility(conn, club, creator)
    if not can_join:
        raise mobile_write_api.ApiFailure(reason or "No podés unirte a esta búsqueda.", HTTPStatus.FORBIDDEN)

    cur = conn.execute(
        """
        UPDATE mobile_match_searches
        SET status='MATCHED', opponent_user_id=?, opponent_club=?, matched_at=CURRENT_TIMESTAMP
        WHERE id=? AND status='OPEN'
        """,
        (int(session["user_id"]), club, int(search_id)),
    )
    if int(cur.rowcount or 0) != 1:
        raise mobile_write_api.ApiFailure("Otro equipo tomó esta búsqueda antes.", HTTPStatus.CONFLICT)

    return {
        "ok": True,
        "id": int(search_id),
        "creator_club": creator,
        "opponent_club": club,
        "status": MATCHED,
        "room_access": {
            "pes_lobby": str(row["pes_lobby"]),
            "room_name": str(row["room_name"]),
            "password": str(row["room_password"] or "") or None,
        },
    }


def cancel_search(conn: sqlite3.Connection, session: dict, search_id: int) -> dict:
    _ensure_schema(conn)
    club = mobile_write_api._require_club(conn, session)
    row = conn.execute(
        "SELECT * FROM mobile_match_searches WHERE id=? LIMIT 1",
        (int(search_id),),
    ).fetchone()
    if not row:
        raise mobile_write_api.ApiFailure("La búsqueda no existe.", HTTPStatus.NOT_FOUND)
    if _norm_team(row["creator_club"]) != _norm_team(club):
        raise mobile_write_api.ApiFailure("Solo el club que creó la búsqueda puede cancelarla.", HTTPStatus.FORBIDDEN)
    if str(row["status"]) not in {OPEN, MATCHED}:
        raise mobile_write_api.ApiFailure("La búsqueda ya está cerrada.", HTTPStatus.CONFLICT)
    conn.execute(
        "UPDATE mobile_match_searches SET status='CANCELLED', cancelled_at=CURRENT_TIMESTAMP WHERE id=?",
        (int(search_id),),
    )
    return {"ok": True, "id": int(search_id), "status": CANCELLED}


def apply_mobile_match_search_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_match_search_patch", False):
        return

    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/match-searches":
            return original_get(self)
        try:
            with mobile_write_api.write_db() as conn:
                mobile_write_api.ensure_schema(conn)
                _ensure_schema(conn)
                session = _optional_session(self.headers, conn)
                payload = searches_payload(conn, session)
                conn.commit()
                self._json(payload)
                return
        except Exception as exc:
            print(f"AJPA match-search GET error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo cargar la búsqueda de partidos."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        parts = mobile_write_api._path_parts(path)
        is_match_route = path == "/api/v1/match-searches" or (
            len(parts) == 5
            and parts[:3] == ["api", "v1", "match-searches"]
            and parts[3].isdigit()
            and parts[4] in {"join", "cancel"}
        )
        if not is_match_route:
            return original_post(self)

        conn = None
        try:
            payload = mobile_write_api._read_json(self)
            conn = mobile_write_api.write_db()
            mobile_write_api.ensure_schema(conn)
            _ensure_schema(conn)
            session = mobile_write_api._session(self.headers, conn)
            if path == "/api/v1/match-searches":
                result = create_search(conn, session, payload)
                conn.commit()
                self._json(result, HTTPStatus.CREATED)
                return
            search_id = int(parts[3])
            if parts[4] == "join":
                result = join_search(conn, session, search_id)
            else:
                result = cancel_search(conn, session, search_id)
            conn.commit()
            self._json(result)
        except mobile_write_api.ApiFailure as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._json({"error": "request", "message": exc.message}, exc.status)
        except sqlite3.IntegrityError:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._json({"error": "conflict", "message": "La búsqueda cambió mientras la procesábamos. Actualizá e intentá de nuevo."}, HTTPStatus.CONFLICT)
        except Exception as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"AJPA match-search POST error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo completar la búsqueda de partido."}, HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            if conn is not None:
                conn.close()

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_match_search_patch = True
    print("AJPA Mobile: Buscar Partido activo • bloquea rivales ya enfrentados según league_matches")
