"""AJPA mobile read-only HTTP API.

This module exposes public league data to the mobile client without importing
Discord and without ever opening SQLite in write mode. It intentionally uses
only SELECT/PRAGMA statements and connects with SQLite ``mode=ro``.

Enable it from the bot process with AJPA_MOBILE_API_ENABLED=1. The league/guild
is selected by AJPA_MOBILE_GUILD_ID, falling back to DISCORD_GUILD_ID.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

FREE_AGENT_CLUB = "Jugador Libre"


def _guild_db_path(base_path: Path, guild_id: int | None) -> Path:
    legacy = int(os.getenv("AJAP_LEGACY_GUILD_ID", "1501062815920816360"))
    if guild_id is None or int(guild_id) == legacy:
        return base_path
    suffix = base_path.suffix or ".db"
    stem = base_path.name[: -len(suffix)] if suffix else base_path.name
    return base_path.with_name(f"{stem}.guild_{int(guild_id)}{suffix}")


def configured_db_path() -> Path:
    base = Path(os.getenv("DB_PATH", "ajap_market.db")).resolve()
    raw_guild = (os.getenv("AJPA_MOBILE_GUILD_ID") or os.getenv("DISCORD_GUILD_ID") or "").strip()
    guild_id = int(raw_guild) if raw_guild else None
    return _guild_db_path(base, guild_id)


def readonly_db() -> sqlite3.Connection:
    path = configured_db_path()
    if not path.exists():
        raise FileNotFoundError(f"AJPA mobile DB not found: {path.name}")
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if table not in _tables(conn):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _player_dict(row: sqlite3.Row) -> dict:
    keys = set(row.keys())
    player_id = int(row["id"]) if "id" in keys and row["id"] is not None else None
    return {
        "id": player_id,
        "code": f"AJAP-{player_id:06d}" if player_id is not None else None,
        "name": row["name"] if "name" in keys else row["player"],
        "position": row["position"] if "position" in keys else None,
        "club": row["club"] if "club" in keys else None,
        "ovr": int(row["rating"]) if "rating" in keys and row["rating"] is not None else None,
        "market_value": int(row["min_sale_value"]) if "min_sale_value" in keys and row["min_sale_value"] is not None else None,
    }


def status_payload(conn: sqlite3.Connection) -> dict:
    tables = _tables(conn)
    market_open = False
    updated_at = None
    if "market_state" in tables:
        row = conn.execute("SELECT * FROM market_state WHERE id=1 LIMIT 1").fetchone()
        if row:
            market_open = bool(row["is_open"])
            updated_at = row["updated_at"] if "updated_at" in row.keys() else None

    season = None
    if "seasons" in tables:
        row = conn.execute("SELECT id, name FROM seasons WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            season = {"id": int(row["id"]), "name": row["name"]}

    return {"market_open": market_open, "market_updated_at": updated_at, "season": season}


def clubs_payload(conn: sqlite3.Connection) -> list[dict]:
    tables = _tables(conn)
    if "league_teams" in tables:
        rows = conn.execute(
            "SELECT name FROM league_teams WHERE active=1 AND TRIM(COALESCE(name,''))<>'' ORDER BY name COLLATE NOCASE"
        ).fetchall()
        names = [str(row["name"]).strip() for row in rows]
    elif "roster_players" in tables:
        rows = conn.execute(
            "SELECT DISTINCT club AS name FROM roster_players WHERE TRIM(COALESCE(club,''))<>'' AND club<>? COLLATE NOCASE ORDER BY club COLLATE NOCASE",
            (FREE_AGENT_CLUB,),
        ).fetchall()
        names = [str(row["name"]).strip() for row in rows]
    else:
        names = []

    result = []
    for name in names:
        balance = None
        if "club_finances" in tables:
            row = conn.execute("SELECT balance FROM club_finances WHERE club=? COLLATE NOCASE LIMIT 1", (name,)).fetchone()
            balance = int(row["balance"]) if row else 0
        roster_count = 0
        if "roster_players" in tables:
            roster_count = int(
                conn.execute("SELECT COUNT(*) AS c FROM roster_players WHERE club=? COLLATE NOCASE", (name,)).fetchone()["c"]
            )
        result.append({"name": name, "balance": balance, "roster_count": roster_count})
    return result


def roster_payload(conn: sqlite3.Connection, club: str) -> list[dict]:
    if "roster_players" not in _tables(conn):
        return []
    cols = _columns(conn, "roster_players")
    rating = "rating" if "rating" in cols else "NULL AS rating"
    value = "min_sale_value" if "min_sale_value" in cols else "NULL AS min_sale_value"
    rows = conn.execute(
        f"SELECT id, name, position, club, {rating}, {value} FROM roster_players WHERE club=? COLLATE NOCASE ORDER BY COALESCE(rating,-1) DESC, name COLLATE NOCASE",
        (club,),
    ).fetchall()
    return [_player_dict(row) for row in rows]


def market_payload(conn: sqlite3.Connection) -> list[dict]:
    tables = _tables(conn)
    if "publications" not in tables:
        return []
    pub_cols = _columns(conn, "publications")
    roster_cols = _columns(conn, "roster_players") if "roster_players" in tables else set()
    operation = "p.operation_type" if "operation_type" in pub_cols else "'TRANSFERENCIA' AS operation_type"
    rating = "r.rating" if "rating" in roster_cols else "NULL AS rating"
    value = "r.min_sale_value" if "min_sale_value" in roster_cols else "NULL AS min_sale_value"
    join = "LEFT JOIN roster_players r ON r.name=p.player COLLATE NOCASE" if "roster_players" in tables else ""
    rows = conn.execute(
        f"""
        SELECT p.id AS publication_id, p.player, p.position, p.club, p.price, p.detail,
               {operation}, {rating}, {value}
        FROM publications p
        {join}
        WHERE p.active=1
        ORDER BY p.id DESC
        LIMIT 200
        """
    ).fetchall()
    result = []
    for row in rows:
        keys = set(row.keys())
        operation_type = str(row["operation_type"] or "TRANSFERENCIA")
        result.append(
            {
                "publication_id": int(row["publication_id"]),
                "player": row["player"],
                "position": row["position"],
                "club": row["club"],
                "price": row["price"],
                "detail": row["detail"],
                "operation_type": operation_type,
                "ovr": int(row["rating"]) if "rating" in keys and row["rating"] is not None else None,
                "market_value": int(row["min_sale_value"]) if "min_sale_value" in keys and row["min_sale_value"] is not None else None,
                "is_free_agent": operation_type.upper() == "JUGADOR LIBRE" or str(row["club"] or "").casefold() == FREE_AGENT_CLUB.casefold(),
            }
        )
    return result


def free_agents_payload(conn: sqlite3.Connection) -> list[dict]:
    return [item for item in market_payload(conn) if item["is_free_agent"]]


def snapshot_payload(conn: sqlite3.Connection) -> dict:
    status = status_payload(conn)
    clubs = clubs_payload(conn)
    market = market_payload(conn)
    return {
        "read_only": True,
        "status": status,
        "clubs": clubs,
        "market": market,
        "free_agents": [item for item in market if item["is_free_agent"]],
    }


class MobileReadHandler(BaseHTTPRequestHandler):
    server_version = "AJPA-Mobile-ReadAPI/0.1"

    def _json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._json({}, HTTPStatus.NO_CONTENT)

    def do_POST(self):
        self._json({"error": "read_only", "message": "La API móvil todavía es solo lectura."}, HTTPStatus.METHOD_NOT_ALLOWED)

    def do_PUT(self):
        self.do_POST()

    def do_PATCH(self):
        self.do_POST()

    def do_DELETE(self):
        self.do_POST()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path in {"/", "/health"}:
                with readonly_db() as conn:
                    conn.execute("SELECT 1").fetchone()
                self._json({"ok": True, "service": "ajpa-mobile-read-api", "read_only": True})
                return

            with readonly_db() as conn:
                if path == "/api/v1/status":
                    self._json(status_payload(conn))
                    return
                if path == "/api/v1/clubs":
                    self._json({"clubs": clubs_payload(conn)})
                    return
                if path == "/api/v1/market":
                    self._json({"market": market_payload(conn)})
                    return
                if path == "/api/v1/free-agents":
                    self._json({"free_agents": free_agents_payload(conn)})
                    return
                if path == "/api/v1/snapshot":
                    self._json(snapshot_payload(conn))
                    return
                prefix = "/api/v1/clubs/"
                suffix = "/roster"
                if path.startswith(prefix) and path.endswith(suffix):
                    club = unquote(path[len(prefix):-len(suffix)]).strip("/")
                    if not club:
                        self._json({"error": "club_required"}, HTTPStatus.BAD_REQUEST)
                        return
                    self._json({"club": club, "players": roster_payload(conn, club)})
                    return

            self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
        except FileNotFoundError as exc:
            self._json({"error": "database_not_found", "message": str(exc)}, HTTPStatus.SERVICE_UNAVAILABLE)
        except Exception as exc:
            print(f"AJPA mobile read API error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, fmt, *args):
        print("AJPA mobile API:", fmt % args)


def start_mobile_read_api() -> ThreadingHTTPServer | None:
    if (os.getenv("AJPA_MOBILE_API_ENABLED") or "0").strip().lower() not in {"1", "true", "yes", "on"}:
        print("AJPA mobile read API disabled (AJPA_MOBILE_API_ENABLED != 1)")
        return None

    host = (os.getenv("AJPA_MOBILE_API_HOST") or "0.0.0.0").strip()
    port = int(os.getenv("PORT") or os.getenv("AJPA_MOBILE_API_PORT") or "8080")
    server = ThreadingHTTPServer((host, port), MobileReadHandler)
    thread = threading.Thread(target=server.serve_forever, name="ajpa-mobile-read-api", daemon=True)
    thread.start()
    print(f"AJPA mobile read API listening on {host}:{port} • SQLite mode=ro")
    return server
