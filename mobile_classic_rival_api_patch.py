"""Fixed classic-rival system shared by AJPA Mobile and the Discord bot database.

A DT proposes another active club as its classic. The rival DT receives a best-
effort Discord DM and can accept or reject from the app. Once accepted, the two
clubs remain paired until the official head-to-head history has a difference of
more than ten wins (11+). Public club profiles expose the classic and live H2H
record calculated from the same league_matches table used by Liga.
"""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from http import HTTPStatus
from urllib.parse import urlparse

import league_automation_patch as league
import mobile_club_profiles_api_patch as profiles
import mobile_read_api
import mobile_write_api

_DISCORD_API = "https://discord.com/api/v10"


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS classic_rival_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_club TEXT NOT NULL COLLATE NOCASE,
            target_club TEXT NOT NULL COLLATE NOCASE,
            requester_user_id INTEGER NOT NULL,
            target_user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            responded_at DATETIME,
            response_user_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS classic_rivals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club_a TEXT NOT NULL COLLATE NOCASE,
            club_b TEXT NOT NULL COLLATE NOCASE,
            accepted_request_id INTEGER,
            accepted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            accepted_by INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            released_at DATETIME,
            released_by INTEGER,
            release_reason TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_classic_requests_status
            ON classic_rival_requests(status, requester_club, target_club);
        CREATE INDEX IF NOT EXISTS idx_classic_rivals_active
            ON classic_rivals(active, club_a, club_b);

        CREATE TABLE IF NOT EXISTS classic_market_outbox (
            classic_id INTEGER PRIMARY KEY,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _canonical(conn: sqlite3.Connection, raw: str) -> str:
    return profiles._canonical_club(conn, raw)


def _owner_id(conn: sqlite3.Connection, club: str) -> int | None:
    row = profiles._owner_row(conn, club)
    return int(row["user_id"]) if row and row["user_id"] is not None else None


def _active_pair(conn: sqlite3.Connection, club: str):
    if "classic_rivals" not in _tables(conn):
        return None
    return conn.execute(
        """
        SELECT * FROM classic_rivals
        WHERE active=1 AND (club_a=? COLLATE NOCASE OR club_b=? COLLATE NOCASE)
        ORDER BY id DESC LIMIT 1
        """,
        (club, club),
    ).fetchone()


def _opponent(row, club: str) -> str:
    return str(row["club_b"] if str(row["club_a"]).casefold() == club.casefold() else row["club_a"])


def _league_name(club: str) -> str:
    try:
        return league.canonical_team(club) or club
    except Exception:
        return club


def _h2h(conn: sqlite3.Connection, club: str, opponent: str) -> dict:
    home = _league_name(club)
    away = _league_name(opponent)
    rows = []
    if "league_matches" in _tables(conn):
        rows = conn.execute(
            """
            SELECT id, home_team, away_team, home_goals, away_goals, created_at
            FROM league_matches
            WHERE (home_team=? COLLATE NOCASE AND away_team=? COLLATE NOCASE)
               OR (home_team=? COLLATE NOCASE AND away_team=? COLLATE NOCASE)
            ORDER BY id DESC
            """,
            (home, away, away, home),
        ).fetchall()

    wins = draws = losses = goals_for = goals_against = 0
    recent: list[dict] = []
    for row in rows:
        is_home = str(row["home_team"]).casefold() == home.casefold()
        gf = int(row["home_goals"] if is_home else row["away_goals"])
        ga = int(row["away_goals"] if is_home else row["home_goals"])
        goals_for += gf
        goals_against += ga
        if gf > ga:
            wins += 1
        elif gf < ga:
            losses += 1
        else:
            draws += 1
        if len(recent) < 10:
            recent.append(
                {
                    "id": int(row["id"]),
                    "home_team": str(row["home_team"]),
                    "away_team": str(row["away_team"]),
                    "home_goals": int(row["home_goals"]),
                    "away_goals": int(row["away_goals"]),
                    "created_at": str(row["created_at"] or ""),
                }
            )

    win_difference = wins - losses
    return {
        "played": len(rows),
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "win_difference": win_difference,
        "release_allowed": abs(win_difference) > 10,
        "last_matches": recent,
    }


def classic_public_payload(conn: sqlite3.Connection, club: str) -> dict | None:
    pair = _active_pair(conn, club)
    if not pair:
        return None
    rival = _opponent(pair, club)
    return {
        "opponent": rival,
        "opponent_manager": profiles._manager_payload(conn, rival),
        "accepted_at": str(pair["accepted_at"] or ""),
        "history": _h2h(conn, club, rival),
    }


def _request_payload(conn: sqlite3.Connection, row, viewer_club: str) -> dict:
    requester = str(row["requester_club"])
    target = str(row["target_club"])
    other = target if requester.casefold() == viewer_club.casefold() else requester
    return {
        "id": int(row["id"]),
        "requester_club": requester,
        "target_club": target,
        "requester_manager": profiles._manager_payload(conn, requester),
        "target_manager": profiles._manager_payload(conn, target),
        "other_club": other,
        "status": str(row["status"]),
        "created_at": str(row["created_at"] or ""),
    }


def my_classic_payload(conn: sqlite3.Connection, headers) -> dict:
    ensure_schema(conn)
    session = mobile_write_api._session(headers, conn)
    club = mobile_write_api._require_club(conn, session)
    current = classic_public_payload(conn, club)

    incoming_rows = conn.execute(
        """
        SELECT * FROM classic_rival_requests
        WHERE target_club=? COLLATE NOCASE AND status='PENDING'
        ORDER BY id DESC
        """,
        (club,),
    ).fetchall()
    outgoing_row = conn.execute(
        """
        SELECT * FROM classic_rival_requests
        WHERE requester_club=? COLLATE NOCASE AND status='PENDING'
        ORDER BY id DESC LIMIT 1
        """,
        (club,),
    ).fetchone()

    active_by_club: set[str] = set()
    for row in conn.execute("SELECT club_a, club_b FROM classic_rivals WHERE active=1").fetchall():
        active_by_club.add(str(row["club_a"]).casefold())
        active_by_club.add(str(row["club_b"]).casefold())

    available = []
    for candidate in mobile_read_api._live_mobile_club_names(conn):
        if candidate.casefold() == club.casefold():
            continue
        manager = profiles._manager_payload(conn, candidate)
        reason = None
        if manager.get("user_id") is None:
            reason = "Sin DT asignado"
        elif candidate.casefold() in active_by_club:
            reason = "Ya tiene clásico rival"
        available.append(
            {
                "club": candidate,
                "manager": manager,
                "available": reason is None and current is None and outgoing_row is None,
                "reason": reason,
            }
        )

    return {
        "club": club,
        "classic": current,
        "incoming": [_request_payload(conn, row, club) for row in incoming_rows],
        "outgoing": _request_payload(conn, outgoing_row, club) if outgoing_row else None,
        "available_clubs": available,
        "rule": {
            "release_win_difference": 11,
            "text": "El clásico es fijo y solo puede liberarse cuando uno de los dos tenga 11 o más victorias de diferencia en el historial entre ambos.",
        },
    }


def _pair_sorted(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b), key=lambda item: item.casefold()))  # type: ignore[return-value]


def _request_classic(conn: sqlite3.Connection, session: dict, payload: dict) -> tuple[dict, tuple[int, str] | None]:
    ensure_schema(conn)
    requester = mobile_write_api._require_club(conn, session)
    target = _canonical(conn, payload.get("target_club"))
    if requester.casefold() == target.casefold():
        raise mobile_write_api.ApiFailure("No podés elegir a tu propio equipo como clásico rival.")
    if _active_pair(conn, requester):
        raise mobile_write_api.ApiFailure("Tu club ya tiene un clásico rival activo.")
    if _active_pair(conn, target):
        raise mobile_write_api.ApiFailure(f"{target} ya tiene un clásico rival activo.")

    existing = conn.execute(
        "SELECT id FROM classic_rival_requests WHERE requester_club=? COLLATE NOCASE AND status='PENDING' LIMIT 1",
        (requester,),
    ).fetchone()
    if existing:
        raise mobile_write_api.ApiFailure("Ya tenés una solicitud de clásico pendiente. Esperá una respuesta o cancelala.")

    requester_user = int(session["user_id"])
    target_user = _owner_id(conn, target)
    if target_user is None:
        raise mobile_write_api.ApiFailure("Ese equipo no tiene un DT asignado para responder la solicitud.")

    cursor = conn.execute(
        """
        INSERT INTO classic_rival_requests
            (requester_club, target_club, requester_user_id, target_user_id)
        VALUES (?, ?, ?, ?)
        """,
        (requester, target, requester_user, target_user),
    )
    request_id = int(cursor.lastrowid)
    message = (
        f"🔥 **{requester} considera que sos su clásico rival.**\n\n"
        f"⚠️ Si aceptás, **{requester}** quedará como clásico rival fijo de **{target}**. "
        "Solo podrá liberarse cuando uno de los dos tenga **11 o más victorias de diferencia** "
        "en el historial entre ambos.\n\n"
        "Abrí **AJPA Transfer Market → Mi Club → Clásico** para **ACEPTAR** o **RECHAZAR**."
    )
    return {"ok": True, "request_id": request_id, "requester_club": requester, "target_club": target}, (target_user, message)


def _respond_classic(conn: sqlite3.Connection, session: dict, payload: dict) -> tuple[dict, tuple[int, str] | None]:
    ensure_schema(conn)
    club = mobile_write_api._require_club(conn, session)
    raw_id = payload.get("request_id")
    if not str(raw_id or "").isdigit():
        raise mobile_write_api.ApiFailure("Solicitud inválida.")
    decision = str(payload.get("decision") or "").strip().upper()
    if decision not in {"ACCEPT", "REJECT"}:
        raise mobile_write_api.ApiFailure("Elegí aceptar o rechazar la solicitud.")

    row = conn.execute(
        "SELECT * FROM classic_rival_requests WHERE id=? LIMIT 1",
        (int(raw_id),),
    ).fetchone()
    if not row or str(row["status"]) != "PENDING":
        raise mobile_write_api.ApiFailure("Esa solicitud ya no está pendiente.", HTTPStatus.NOT_FOUND)
    target = str(row["target_club"])
    requester = str(row["requester_club"])
    if target.casefold() != club.casefold() or int(row["target_user_id"]) != int(session["user_id"]):
        raise mobile_write_api.ApiFailure("Solo el DT del equipo invitado puede responder.", HTTPStatus.FORBIDDEN)

    if decision == "REJECT":
        conn.execute(
            """
            UPDATE classic_rival_requests
            SET status='REJECTED', responded_at=CURRENT_TIMESTAMP, response_user_id=?
            WHERE id=?
            """,
            (int(session["user_id"]), int(raw_id)),
        )
        msg = f"❌ **{target} rechazó** la propuesta de clásico rival de **{requester}**."
        return {"ok": True, "status": "REJECTED", "requester_club": requester, "target_club": target}, (int(row["requester_user_id"]), msg)

    if _active_pair(conn, requester) or _active_pair(conn, target):
        raise mobile_write_api.ApiFailure("Uno de los dos equipos ya tiene un clásico rival activo.")

    club_a, club_b = _pair_sorted(requester, target)
    pair_cursor = conn.execute(
        """
        INSERT INTO classic_rivals
            (club_a, club_b, accepted_request_id, accepted_by)
        VALUES (?, ?, ?, ?)
        """,
        (club_a, club_b, int(raw_id), int(session["user_id"])),
    )
    conn.execute(
        """
        UPDATE classic_rival_requests
        SET status='ACCEPTED', responded_at=CURRENT_TIMESTAMP, response_user_id=?
        WHERE id=?
        """,
        (int(session["user_id"]), int(raw_id)),
    )
    # Once a pair becomes official, every other pending proposal involving either
    # club is stale and must not be accepted later.
    conn.execute(
        """
        UPDATE classic_rival_requests
        SET status='CANCELLED_CONFLICT', responded_at=CURRENT_TIMESTAMP
        WHERE status='PENDING' AND id<>? AND (
            requester_club IN (?, ?) COLLATE NOCASE OR target_club IN (?, ?) COLLATE NOCASE
        )
        """,
        (int(raw_id), requester, target, requester, target),
    )
    msg = (
        f"🔥 **{target} aceptó. {requester} vs {target} ya es un clásico oficial de AJPA.**\n\n"
        "El historial se actualizará automáticamente con cada resultado oficial de Liga."
    )
    # The bot publishes only after this transaction commits, for both clients.
    conn.execute(
        "INSERT INTO classic_market_outbox (classic_id) VALUES (?)",
        (int(pair_cursor.lastrowid),),
    )
    return {
        "ok": True,
        "status": "ACCEPTED",
        "classic_id": int(pair_cursor.lastrowid),
        "requester_club": requester,
        "target_club": target,
    }, (int(row["requester_user_id"]), msg)


def _cancel_request(conn: sqlite3.Connection, session: dict, payload: dict) -> dict:
    ensure_schema(conn)
    club = mobile_write_api._require_club(conn, session)
    raw_id = payload.get("request_id")
    if not str(raw_id or "").isdigit():
        raise mobile_write_api.ApiFailure("Solicitud inválida.")
    row = conn.execute(
        "SELECT * FROM classic_rival_requests WHERE id=? LIMIT 1",
        (int(raw_id),),
    ).fetchone()
    if not row or str(row["status"]) != "PENDING":
        raise mobile_write_api.ApiFailure("Esa solicitud ya no está pendiente.", HTTPStatus.NOT_FOUND)
    if str(row["requester_club"]).casefold() != club.casefold() or int(row["requester_user_id"]) != int(session["user_id"]):
        raise mobile_write_api.ApiFailure("Solo quien envió la solicitud puede cancelarla.", HTTPStatus.FORBIDDEN)
    conn.execute(
        "UPDATE classic_rival_requests SET status='CANCELLED', responded_at=CURRENT_TIMESTAMP WHERE id=?",
        (int(raw_id),),
    )
    return {"ok": True, "status": "CANCELLED"}


def _release_classic(conn: sqlite3.Connection, session: dict, payload: dict) -> dict:
    del payload
    ensure_schema(conn)
    club = mobile_write_api._require_club(conn, session)
    pair = _active_pair(conn, club)
    if not pair:
        raise mobile_write_api.ApiFailure("Tu club no tiene un clásico rival activo.", HTTPStatus.NOT_FOUND)
    rival = _opponent(pair, club)
    history = _h2h(conn, club, rival)
    if not history["release_allowed"]:
        raise mobile_write_api.ApiFailure(
            "El clásico es fijo. Solo puede liberarse cuando uno de los dos tenga 11 o más victorias de diferencia en el historial entre ambos.",
            HTTPStatus.CONFLICT,
        )
    conn.execute(
        """
        UPDATE classic_rivals
        SET active=0, released_at=CURRENT_TIMESTAMP, released_by=?,
            release_reason='H2H_WIN_DIFFERENCE_OVER_10'
        WHERE id=?
        """,
        (int(session["user_id"]), int(pair["id"])),
    )
    return {"ok": True, "released": True, "club": club, "opponent": rival, "history": history}


def _discord_json(path: str, method: str = "GET", payload: dict | None = None) -> dict | list | None:
    token = str(os.getenv("DISCORD_TOKEN") or "").strip()
    if not token:
        return None
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{_DISCORD_API}{path}",
        method=method,
        data=data,
        headers={
            "Authorization": f"Bot {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "AJPA-Transfer-Market-Mobile/0.3",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _send_dm(user_id: int, content: str) -> None:
    try:
        channel = _discord_json("/users/@me/channels", "POST", {"recipient_id": str(int(user_id))})
        channel_id = str((channel or {}).get("id") or "") if isinstance(channel, dict) else ""
        if not channel_id:
            return
        _discord_json(f"/channels/{channel_id}/messages", "POST", {"content": content[:1900]})
    except Exception:
        return


def apply_mobile_classic_rival_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_classic_rival_patch", False):
        return

    try:
        with mobile_write_api.write_db() as conn:
            ensure_schema(conn)
            conn.commit()
    except Exception as exc:
        print(f"AJPA classic rival schema warning: {type(exc).__name__}: {exc}")

    # Enrich the existing public club summary/profile payload without duplicating
    # its economy/title/roster implementation.
    original_summary = profiles._summary_for
    if not getattr(original_summary, "_ajpa_classic_wrapped", False):
        def summary_with_classic(conn: sqlite3.Connection, canonical: str) -> dict:
            data = original_summary(conn, canonical)
            data["classic"] = classic_public_payload(conn, canonical)
            return data
        summary_with_classic._ajpa_classic_wrapped = True
        profiles._summary_for = summary_with_classic

    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/my/classic":
            return original_get(self)
        try:
            with mobile_write_api.write_db() as conn:
                self._json(my_classic_payload(conn, self.headers))
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            print(f"AJPA classic rival GET error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo cargar el clásico rival."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        actions = {
            "/api/v1/my/classic/request": _request_classic,
            "/api/v1/my/classic/respond": _respond_classic,
            "/api/v1/my/classic/cancel": _cancel_request,
            "/api/v1/my/classic/release": _release_classic,
        }
        action = actions.get(path)
        if action is None:
            return original_post(self)

        conn = None
        notification = None
        try:
            payload = mobile_write_api._read_json(self)
            conn = mobile_write_api.write_db()
            ensure_schema(conn)
            session = mobile_write_api._session(self.headers, conn)
            conn.execute("BEGIN IMMEDIATE")
            result = action(conn, session, payload)
            if isinstance(result, tuple):
                result, notification = result
            conn.commit()
            self._json(result)
            if notification:
                _send_dm(notification[0], notification[1])
        except mobile_write_api.ApiFailure as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"AJPA classic rival POST error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo completar la operación de clásico rival."}, HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            if conn is not None:
                conn.close()

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_classic_rival_patch = True
    print("AJPA Mobile: clásicos rivales fijos + H2H + notificaciones Discord activos")
