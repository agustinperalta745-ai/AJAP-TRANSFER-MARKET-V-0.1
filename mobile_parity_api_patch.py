"""Extra endpoints used by the mobile Discord-parity screens.

Keeps public Liga/history reads read-only and exposes only narrowly scoped Staff
operations behind the same paired mobile session used by the market API.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_read_api
import mobile_write_api


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def league_payload(conn: sqlite3.Connection) -> dict:
    tables = _tables(conn)
    teams = list(mobile_read_api._live_mobile_club_names(conn))
    table = {
        team: {
            "team": team,
            "pj": 0,
            "pg": 0,
            "pe": 0,
            "pp": 0,
            "gf": 0,
            "gc": 0,
            "dg": 0,
            "pts": 0,
        }
        for team in teams
    }

    match_where = ""
    match_params: tuple = ()
    active_competition = None
    if "competition_cycle_state" in tables:
        row = conn.execute(
            "SELECT phase, competition_id FROM competition_cycle_state WHERE id=1 LIMIT 1"
        ).fetchone()
        if row and str(row["phase"] or "") in {"preseason", "season", "cup"} and row["competition_id"] is not None:
            active_competition = int(row["competition_id"])
            if "league_matches" in tables and "competition_id" in mobile_read_api._columns(conn, "league_matches"):
                match_where = " WHERE competition_id=?"
                match_params = (active_competition,)

    result_cards = []
    if "league_matches" in tables:
        rows = conn.execute(
            "SELECT id, home_team, away_team, home_goals, away_goals, COALESCE(created_at, CURRENT_TIMESTAMP) AS created_at FROM league_matches" + match_where + " ORDER BY id ASC",
            match_params,
        ).fetchall()
        for row in rows:
            home_name = str(row["home_team"] or "").strip()
            away_name = str(row["away_team"] or "").strip()
            if home_name and home_name not in table:
                table[home_name] = {"team": home_name, "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "dg": 0, "pts": 0}
            if away_name and away_name not in table:
                table[away_name] = {"team": away_name, "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "dg": 0, "pts": 0}
            home = table.get(home_name)
            away = table.get(away_name)
            if not home or not away:
                continue
            hg, ag = int(row["home_goals"]), int(row["away_goals"])
            result_cards.append({
                "id": int(row["id"]),
                "home_team": home_name,
                "away_team": away_name,
                "home_goals": hg,
                "away_goals": ag,
                "created_at": str(row["created_at"] or ""),
            })
            home["pj"] += 1
            away["pj"] += 1
            home["gf"] += hg
            home["gc"] += ag
            away["gf"] += ag
            away["gc"] += hg
            if hg > ag:
                home["pg"] += 1
                away["pp"] += 1
                home["pts"] += 3
            elif ag > hg:
                away["pg"] += 1
                home["pp"] += 1
                away["pts"] += 3
            else:
                home["pe"] += 1
                away["pe"] += 1
                home["pts"] += 1
                away["pts"] += 1

    standings = list(table.values())
    for row in standings:
        row["dg"] = int(row["gf"]) - int(row["gc"])
    standings.sort(
        key=lambda row: (
            -int(row["pts"]),
            -int(row["dg"]),
            -int(row["gf"]),
            -int(row["pg"]),
            str(row["team"]).casefold(),
        )
    )

    scorers = []
    if "league_goal_events" in tables:
        goal_where = ""
        goal_params: tuple = ()
        if active_competition is not None and "competition_id" in mobile_read_api._columns(conn, "league_goal_events"):
            goal_where = " WHERE competition_id=?"
            goal_params = (active_competition,)
        rows = conn.execute(
            """
            SELECT player, team, SUM(goals) AS goals
            FROM league_goal_events
            """ + goal_where + """
            GROUP BY player COLLATE NOCASE, COALESCE(team, '') COLLATE NOCASE
            ORDER BY goals DESC, player COLLATE NOCASE ASC
            LIMIT 50
            """,
            goal_params,
        ).fetchall()
        scorers = [
            {
                "player": str(row["player"]),
                "team": str(row["team"] or ""),
                "goals": int(row["goals"] or 0),
            }
            for row in rows
            if str(row["player"] or "").strip()
        ]

    return {"standings": standings, "scorers": scorers, "result_cards": result_cards, "matches": result_cards}


def history_payload(conn: sqlite3.Connection, limit: int = 100) -> dict:
    if "transfers" not in _tables(conn):
        return {"items": []}
    cols = mobile_read_api._columns(conn, "transfers")
    wanted = [
        "id", "player", "seller", "buyer", "amount", "status", "operation_type",
        "created_at", "approved_at", "applied_at", "notes",
    ]
    selected = [name for name in wanted if name in cols]
    if not selected:
        return {"items": []}
    rows = conn.execute(
        f"SELECT {', '.join(selected)} FROM transfers ORDER BY id DESC LIMIT ?",
        (max(1, min(int(limit), 200)),),
    ).fetchall()
    items = []
    for row in rows:
        keys = set(row.keys())
        items.append({
            "id": int(row["id"]) if "id" in keys and row["id"] is not None else 0,
            "player": str(row["player"] or "") if "player" in keys else "",
            "seller": str(row["seller"] or "") if "seller" in keys else "",
            "buyer": str(row["buyer"] or "") if "buyer" in keys else "",
            "amount": str(row["amount"] or "$0") if "amount" in keys else "$0",
            "status": str(row["status"] or "") if "status" in keys else "",
            "operation_type": str(row["operation_type"] or "TRANSFERENCIA") if "operation_type" in keys else "TRANSFERENCIA",
            "created_at": str(row["created_at"] or "") if "created_at" in keys else "",
            "approved_at": str(row["approved_at"] or "") if "approved_at" in keys else "",
            "applied_at": str(row["applied_at"] or "") if "applied_at" in keys else "",
            "notes": str(row["notes"] or "") if "notes" in keys else "",
        })
    return {"items": items}


def _staff_session(headers, conn: sqlite3.Connection) -> dict:
    session = mobile_write_api._session(headers, conn)
    if not session.get("is_staff"):
        raise mobile_write_api.ApiFailure("Esta herramienta es exclusiva para Staff.", HTTPStatus.FORBIDDEN)
    return session


def assignments_payload(conn: sqlite3.Connection) -> dict:
    if "clubs" not in _tables(conn):
        return {"assignments": []}
    cols = mobile_read_api._columns(conn, "clubs")
    if not {"user_id", "name"}.issubset(cols):
        return {"assignments": []}
    rows = conn.execute(
        "SELECT user_id, name FROM clubs WHERE user_id IS NOT NULL AND TRIM(COALESCE(name,''))<>'' ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return {
        "assignments": [
            {"user_id": str(row["user_id"]), "club": str(row["name"])}
            for row in rows
        ]
    }


def set_market_state(conn: sqlite3.Connection, session: dict, opened: bool) -> dict:
    value = 1 if opened else 0
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_open INTEGER NOT NULL DEFAULT 0,
            updated_by INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS market_state_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            is_open INTEGER NOT NULL,
            changed_by INTEGER,
            changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT OR IGNORE INTO market_state (id, is_open) VALUES (1, 0);
        """
    )
    previous = conn.execute("SELECT is_open FROM market_state WHERE id=1").fetchone()
    old = int(previous["is_open"]) if previous else None
    conn.execute(
        """
        INSERT INTO market_state (id, is_open, updated_by, updated_at)
        VALUES (1, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            is_open=excluded.is_open,
            updated_by=excluded.updated_by,
            updated_at=CURRENT_TIMESTAMP
        """,
        (value, int(session["user_id"])),
    )
    if old != value:
        conn.execute(
            "INSERT INTO market_state_history (is_open, changed_by) VALUES (?, ?)",
            (value, int(session["user_id"])),
        )
    return {"ok": True, "market_open": bool(value)}


def apply_mobile_parity_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_parity_api_patch", False):
        return

    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/api/v1/league":
                with mobile_read_api.readonly_db() as conn:
                    self._json(league_payload(conn))
                return
            if path == "/api/v1/history":
                with mobile_read_api.readonly_db() as conn:
                    self._json(history_payload(conn))
                return
            if path == "/api/v1/admin/assignments":
                with mobile_write_api.write_db() as conn:
                    _staff_session(self.headers, conn)
                    self._json(assignments_payload(conn))
                return
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
            return
        except Exception as exc:
            print(f"AJPA mobile parity GET error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo cargar esta sección."}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        return original_get(self)

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/admin/market":
            return original_post(self)
        conn = None
        try:
            payload = mobile_write_api._read_json(self)
            with mobile_write_api.write_db() as conn:
                mobile_write_api.ensure_schema(conn)
                session = _staff_session(self.headers, conn)
                opened = payload.get("open")
                if not isinstance(opened, bool):
                    raise mobile_write_api.ApiFailure("Indicá el nuevo estado del mercado.")
                result = set_market_state(conn, session, opened)
                conn.commit()
                self._json(result)
                return
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
            print(f"AJPA mobile parity POST error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo completar la operación."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_parity_api_patch = True
