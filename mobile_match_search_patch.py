"""Public AJPA Mobile rival-search board backed by official league results.

Every paired club can publish one active PES room. Searches expire after 30
minutes when nobody takes them. When another eligible club starts searching,
the oldest compatible open search is paired automatically. Once the result bot
persists that fixture in ``league_matches``, the same match-search record becomes
COMPLETED and exposes the official final score to both participants.
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
EXPIRED = "EXPIRED"
SEARCH_TTL_MINUTES = 30


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
        "real betis": "betis",
        "atletico de madrid": "atletico madrid",
        "real zaragoza": "zaragoza",
        "celta de vigo": "celta",
        "olympique de lyon": "lyon",
        "olympique lyon": "lyon",
        "olympique de marsella": "marsella",
        "olympique marsella": "marsella",
        "olympique marseille": "marsella",
        "marseille": "marsella",
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
            cancelled_at DATETIME,
            expired_at DATETIME,
            result_home_team TEXT,
            result_away_team TEXT,
            result_home_goals INTEGER,
            result_away_goals INTEGER,
            result_source_message_id INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_mobile_match_search_status
            ON mobile_match_searches(status, id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mobile_match_search_open_club
            ON mobile_match_searches(creator_club COLLATE NOCASE)
            WHERE status='OPEN';
        """
    )
    cols = mobile_write_api._columns(conn, "mobile_match_searches")
    additions = {
        "completed_at": "DATETIME",
        "expired_at": "DATETIME",
        "result_home_team": "TEXT",
        "result_away_team": "TEXT",
        "result_home_goals": "INTEGER",
        "result_away_goals": "INTEGER",
        "result_source_message_id": "INTEGER",
    }
    for name, sql_type in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE mobile_match_searches ADD COLUMN {name} {sql_type}")


def _expire_stale_open(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE mobile_match_searches
        SET status='EXPIRED', expired_at=CURRENT_TIMESTAMP
        WHERE status='OPEN'
          AND datetime(created_at) <= datetime('now', ?)
        """,
        (f"-{SEARCH_TTL_MINUTES} minutes",),
    )


def _official_result(conn: sqlite3.Connection, club_a: str, club_b: str):
    if not mobile_write_api._table_exists(conn, "league_matches"):
        return None
    a = _norm_team(club_a)
    b = _norm_team(club_b)
    if not a or not b:
        return None
    try:
        rows = conn.execute(
            """
            SELECT id, source_message_id, home_team, away_team, home_goals, away_goals
            FROM league_matches
            ORDER BY id DESC
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    for row in rows:
        home = _norm_team(row["home_team"])
        away = _norm_team(row["away_team"])
        if {home, away} == {a, b}:
            return row
    return None


def _already_played(conn: sqlite3.Connection, club_a: str, club_b: str) -> bool:
    return _official_result(conn, club_a, club_b) is not None


def _reconcile_completed(conn: sqlite3.Connection) -> None:
    """Attach the official result to matched searches as soon as the bot stores it."""
    rows = conn.execute(
        """
        SELECT id, status, creator_club, opponent_club
        FROM mobile_match_searches
        WHERE opponent_club IS NOT NULL
          AND (
                status='MATCHED'
                OR (status='COMPLETED' AND result_home_goals IS NULL)
              )
        """
    ).fetchall()
    for row in rows:
        result = _official_result(
            conn, str(row["creator_club"]), str(row["opponent_club"])
        )
        if not result:
            continue
        conn.execute(
            """
            UPDATE mobile_match_searches
            SET status='COMPLETED',
                completed_at=COALESCE(completed_at, CURRENT_TIMESTAMP),
                result_home_team=?,
                result_away_team=?,
                result_home_goals=?,
                result_away_goals=?,
                result_source_message_id=?
            WHERE id=?
              AND status IN ('MATCHED', 'COMPLETED')
            """,
            (
                str(result["home_team"]),
                str(result["away_team"]),
                int(result["home_goals"]),
                int(result["away_goals"]),
                int(result["source_message_id"]),
                int(row["id"]),
            ),
        )


def _active_search_for_club(conn: sqlite3.Connection, club: str):
    _expire_stale_open(conn)
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


def _eligibility(
    conn: sqlite3.Connection, viewer_club: str | None, creator_club: str
) -> tuple[bool, str | None]:
    _expire_stale_open(conn)
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


def _room_access(row) -> dict:
    return {
        "pes_lobby": str(row["pes_lobby"]),
        "room_name": str(row["room_name"]),
        "password": str(row["room_password"] or "") or None,
    }


def searches_payload(conn: sqlite3.Connection, session: dict | None) -> dict:
    _ensure_schema(conn)
    _expire_stale_open(conn)
    _reconcile_completed(conn)
    viewer_club = None
    if session:
        viewer_club = mobile_write_api.mobile_auth.resolve_club_readonly(
            conn, int(session["user_id"])
        )

    rows = conn.execute(
        """
        SELECT *,
               strftime('%Y-%m-%dT%H:%M:%SZ',
                        datetime(created_at, '+' || ? || ' minutes')) AS expires_at
        FROM mobile_match_searches
        WHERE status='OPEN'
           OR (
                status IN ('MATCHED', 'COMPLETED')
                AND ? IS NOT NULL
                AND (creator_club=? COLLATE NOCASE OR opponent_club=? COLLATE NOCASE)
              )
        ORDER BY CASE status
                   WHEN 'OPEN' THEN 0
                   WHEN 'MATCHED' THEN 1
                   ELSE 2
                 END,
                 id DESC
        LIMIT 150
        """,
        (SEARCH_TTL_MINUTES, viewer_club, viewer_club, viewer_club),
    ).fetchall()

    items = []
    completed_added = False
    for row in rows:
        status = str(row["status"])
        if status == COMPLETED:
            if completed_added:
                continue
            completed_added = True

        is_owner = bool(
            viewer_club
            and _norm_team(viewer_club) == _norm_team(row["creator_club"])
        )
        is_opponent = bool(
            viewer_club
            and row["opponent_club"]
            and _norm_team(viewer_club) == _norm_team(row["opponent_club"])
        )
        can_join, reason = (False, None)
        if status == OPEN:
            can_join, reason = _eligibility(
                conn, viewer_club, str(row["creator_club"])
            )

        item = {
            "id": int(row["id"]),
            "creator_club": str(row["creator_club"]),
            "status": status,
            "opponent_club": str(row["opponent_club"] or "") or None,
            "created_at": str(row["created_at"] or ""),
            "expires_at": str(row["expires_at"] or "") or None,
            "matched_at": str(row["matched_at"] or "") or None,
            "completed_at": str(row["completed_at"] or "") or None,
            "is_owner": is_owner,
            "is_opponent": is_opponent,
            "can_join": bool(can_join),
            "blocked_reason": reason,
            "result": None,
        }
        if status == COMPLETED and row["result_home_team"] is not None:
            item["result"] = {
                "home_team": str(row["result_home_team"]),
                "away_team": str(row["result_away_team"]),
                "home_goals": int(row["result_home_goals"]),
                "away_goals": int(row["result_away_goals"]),
            }
        if status == MATCHED and (is_owner or is_opponent):
            item["room_access"] = _room_access(row)
        items.append(item)

    return {"items": items, "viewer_club": viewer_club}


def _begin_immediate(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")


def _find_auto_match(conn: sqlite3.Connection, club: str):
    rows = conn.execute(
        """
        SELECT *
        FROM mobile_match_searches
        WHERE status='OPEN'
        ORDER BY datetime(created_at) ASC, id ASC
        """
    ).fetchall()
    for row in rows:
        creator = str(row["creator_club"])
        if _norm_team(creator) == _norm_team(club):
            continue
        if _already_played(conn, club, creator):
            continue
        if _matched_search_for_club(conn, creator):
            continue
        return row
    return None


def create_search(conn: sqlite3.Connection, session: dict, payload: dict) -> dict:
    _ensure_schema(conn)
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

    _begin_immediate(conn)
    _expire_stale_open(conn)
    _reconcile_completed(conn)
    if _active_search_for_club(conn, club):
        raise mobile_write_api.ApiFailure(
            "Tu club ya tiene una búsqueda de rival activa.", HTTPStatus.CONFLICT
        )
    if _matched_search_for_club(conn, club):
        raise mobile_write_api.ApiFailure(
            "Tu club ya tiene un rival encontrado.", HTTPStatus.CONFLICT
        )

    candidate = _find_auto_match(conn, club)
    if candidate:
        candidate_id = int(candidate["id"])
        creator = str(candidate["creator_club"])
        cur = conn.execute(
            """
            UPDATE mobile_match_searches
            SET status='MATCHED',
                opponent_user_id=?,
                opponent_club=?,
                matched_at=CURRENT_TIMESTAMP
            WHERE id=? AND status='OPEN'
            """,
            (int(session["user_id"]), club, candidate_id),
        )
        if int(cur.rowcount or 0) != 1:
            raise mobile_write_api.ApiFailure(
                "Otro equipo tomó esa búsqueda antes. Intentá de nuevo.",
                HTTPStatus.CONFLICT,
            )
        return {
            "ok": True,
            "id": candidate_id,
            "creator_club": creator,
            "opponent_club": club,
            "status": MATCHED,
            "auto_matched": True,
            "room_access": _room_access(candidate),
        }

    cur = conn.execute(
        """
        INSERT INTO mobile_match_searches
            (creator_user_id, creator_club, pes_lobby, room_name, room_password, status)
        VALUES (?, ?, ?, ?, ?, 'OPEN')
        """,
        (int(session["user_id"]), club, lobby, room, password or None),
    )
    search_id = int(cur.lastrowid)
    expiry = conn.execute(
        """
        SELECT strftime('%Y-%m-%dT%H:%M:%SZ',
                        datetime(created_at, '+' || ? || ' minutes')) AS expires_at
        FROM mobile_match_searches WHERE id=?
        """,
        (SEARCH_TTL_MINUTES, search_id),
    ).fetchone()
    return {
        "ok": True,
        "id": search_id,
        "creator_club": club,
        "status": OPEN,
        "expires_at": str(expiry["expires_at"] or "") or None,
    }


def join_search(conn: sqlite3.Connection, session: dict, search_id: int) -> dict:
    _ensure_schema(conn)
    club = mobile_write_api._require_club(conn, session)
    _begin_immediate(conn)
    _expire_stale_open(conn)
    _reconcile_completed(conn)
    row = conn.execute(
        "SELECT * FROM mobile_match_searches WHERE id=? LIMIT 1",
        (int(search_id),),
    ).fetchone()
    if not row or str(row["status"]) != OPEN:
        raise mobile_write_api.ApiFailure(
            "Esa búsqueda ya no está disponible.", HTTPStatus.CONFLICT
        )

    creator = str(row["creator_club"])
    can_join, reason = _eligibility(conn, club, creator)
    if not can_join:
        raise mobile_write_api.ApiFailure(
            reason or "No podés unirte a esta búsqueda.", HTTPStatus.FORBIDDEN
        )

    cur = conn.execute(
        """
        UPDATE mobile_match_searches
        SET status='MATCHED', opponent_user_id=?, opponent_club=?, matched_at=CURRENT_TIMESTAMP
        WHERE id=? AND status='OPEN'
        """,
        (int(session["user_id"]), club, int(search_id)),
    )
    if int(cur.rowcount or 0) != 1:
        raise mobile_write_api.ApiFailure(
            "Otro equipo tomó esta búsqueda antes.", HTTPStatus.CONFLICT
        )

    return {
        "ok": True,
        "id": int(search_id),
        "creator_club": creator,
        "opponent_club": club,
        "status": MATCHED,
        "auto_matched": False,
        "room_access": _room_access(row),
    }


def cancel_search(conn: sqlite3.Connection, session: dict, search_id: int) -> dict:
    _ensure_schema(conn)
    club = mobile_write_api._require_club(conn, session)
    _expire_stale_open(conn)
    _reconcile_completed(conn)
    row = conn.execute(
        "SELECT * FROM mobile_match_searches WHERE id=? LIMIT 1",
        (int(search_id),),
    ).fetchone()
    if not row:
        raise mobile_write_api.ApiFailure("La búsqueda no existe.", HTTPStatus.NOT_FOUND)
    if _norm_team(row["creator_club"]) != _norm_team(club):
        raise mobile_write_api.ApiFailure(
            "Solo el club que creó la búsqueda puede cancelarla.",
            HTTPStatus.FORBIDDEN,
        )
    if str(row["status"]) not in {OPEN, MATCHED}:
        raise mobile_write_api.ApiFailure(
            "La búsqueda ya está cerrada.", HTTPStatus.CONFLICT
        )
    conn.execute(
        """
        UPDATE mobile_match_searches
        SET status='CANCELLED', cancelled_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
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
            self._json(
                {
                    "error": "internal_error",
                    "message": "No se pudo cargar la búsqueda de partidos.",
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

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
            self._json(
                {
                    "error": "conflict",
                    "message": "La búsqueda cambió mientras la procesábamos. Actualizá e intentá de nuevo.",
                },
                HTTPStatus.CONFLICT,
            )
        except Exception as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"AJPA match-search POST error: {type(exc).__name__}: {exc}")
            self._json(
                {
                    "error": "internal_error",
                    "message": "No se pudo completar la búsqueda de partido.",
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        finally:
            if conn is not None:
                conn.close()

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_match_search_patch = True
    print(
        "AJPA Mobile: Buscar Partido activo • 30 min • auto-pair • resultado final desde league_matches"
    )
