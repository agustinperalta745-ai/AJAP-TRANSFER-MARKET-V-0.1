"""AJPA mobile read-only HTTP API.

This module exposes public league data to the mobile client without importing
Discord and without ever opening SQLite in write mode. It intentionally uses
only SELECT/PRAGMA statements and connects with SQLite ``mode=ro``.

Enable it from the bot process with AJPA_MOBILE_API_ENABLED=1. The league/guild
is selected by AJPA_MOBILE_GUILD_ID, falling back to DISCORD_GUILD_ID.

The mobile club catalog is also read-only: it mirrors the same JSON-backed club
catalog used by Discord, but it never activates/deactivates rows in SQLite.
Legacy aliases may remain in the DB for history without being exposed as
separate clubs in the APK.
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
DATA_DIR = Path(__file__).resolve().parent / "data"

# Canonical JSON club -> historical DB aliases. These are lookup fallbacks only:
# the APK always displays the canonical JSON name.
CLUB_LOOKUP_ALIASES = {
    "real betis": ("Betis",),
    "sevilla fc": ("Sevilla",),
    "villarreal cf": ("Villarreal", "Villareal", "Villareal CF"),
}


def _guild_db_path(base_path: Path, guild_id: int | None) -> Path:
    legacy = int(os.getenv("AJAP_LEGACY_GUILD_ID", "1501062815920816360"))
    if guild_id is None or int(guild_id) == legacy:
        return base_path
    suffix = base_path.suffix or ".db"
    stem = base_path.name[: -len(suffix)] if suffix else base_path.name
    return base_path.with_name(f"{stem}.guild_{int(guild_id)}{suffix}")


def configured_db_path() -> Path:
    base = Path(os.getenv("DB_PATH", "ajap_market.db")).resolve()
    raw_guild = (
        os.getenv("AJPA_MOBILE_GUILD_ID")
        or os.getenv("DISCORD_GUILD_ID")
        or ""
    ).strip()
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
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if table not in _tables(conn):
        return set()
    return {
        str(row["name"])
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def _json_payload_sources():
    """Yield parsed normal and multipart roster JSON payloads."""
    for path in sorted(DATA_DIR.glob("*.json"), key=lambda item: item.name.casefold()):
        try:
            yield path.name, json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"AJPA mobile catalog: ignored invalid {path.name}: {exc}")

    multipart: dict[str, list[tuple[int, Path]]] = {}
    for part in DATA_DIR.glob("*.json.part*"):
        prefix, separator, suffix = part.name.rpartition(".part")
        if not separator or not prefix.casefold().endswith(".json") or not suffix.isdigit():
            continue
        multipart.setdefault(prefix, []).append((int(suffix), part))

    for prefix in sorted(multipart, key=str.casefold):
        parts = sorted(multipart[prefix], key=lambda item: item[0])
        try:
            text = "".join(path.read_text(encoding="utf-8") for _index, path in parts)
            yield f"{prefix}.part*", json.loads(text)
        except Exception as exc:
            print(f"AJPA mobile catalog: ignored invalid multipart {prefix}: {exc}")


def _json_source_team_names() -> list[str]:
    """Return the canonical club names exposed by Discord's JSON catalog."""
    names: list[str] = []
    seen: set[str] = set()
    for _source, payload in _json_payload_sources():
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("equipo") or "").strip()
        players = payload.get("jugadores")
        key = name.casefold()
        if not name or not isinstance(players, list) or not players or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return sorted(names, key=str.casefold)


def _deleted_team_keys(conn: sqlite3.Connection) -> set[str]:
    if "deleted_teams" not in _tables(conn):
        return set()
    rows = conn.execute(
        """
        SELECT name
        FROM deleted_teams
        WHERE name IS NOT NULL AND TRIM(name) <> ''
        """
    ).fetchall()
    return {str(row["name"]).strip().casefold() for row in rows}


def _live_mobile_club_names(conn: sqlite3.Connection) -> list[str]:
    """Read the same canonical club catalog Discord exposes, without DB writes."""
    json_names = _json_source_team_names()
    if json_names:
        deleted = _deleted_team_keys(conn)
        return [name for name in json_names if name.casefold() not in deleted]

    # Safe fallback for installations without JSON-backed rosters.
    tables = _tables(conn)
    if "league_teams" in tables:
        rows = conn.execute(
            """
            SELECT name
            FROM league_teams
            WHERE active=1
              AND TRIM(COALESCE(name,''))<>''
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
        return [str(row["name"]).strip() for row in rows]

    if "roster_players" in tables:
        rows = conn.execute(
            """
            SELECT DISTINCT club AS name
            FROM roster_players
            WHERE TRIM(COALESCE(club,''))<>''
              AND club<>? COLLATE NOCASE
            ORDER BY club COLLATE NOCASE
            """,
            (FREE_AGENT_CLUB,),
        ).fetchall()
        return [str(row["name"]).strip() for row in rows]

    return []


def _candidate_db_club_names(canonical: str) -> list[str]:
    raw = str(canonical or "").strip()
    if not raw:
        return []

    candidates = [raw]
    candidates.extend(CLUB_LOOKUP_ALIASES.get(raw.casefold(), ()))

    # Generic historical suffix fallback.
    upper = raw.upper()
    for suffix in (" FC", " CF"):
        if upper.endswith(suffix):
            candidates.append(raw[: -len(suffix)].strip())

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.casefold()
        if candidate and key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def _resolve_db_club_name(conn: sqlite3.Connection, canonical: str) -> str:
    """Find the DB spelling that actually contains the canonical club's data."""
    tables = _tables(conn)
    candidates = _candidate_db_club_names(canonical)
    if not candidates:
        return canonical

    # Prefer the candidate with the largest actual roster. This avoids stale
    # one-player aliases such as Sevilla/Villarreal winning over the real club.
    if "roster_players" in tables:
        scored: list[tuple[int, int, str]] = []
        for index, candidate in enumerate(candidates):
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM roster_players
                WHERE club=? COLLATE NOCASE
                """,
                (candidate,),
            ).fetchone()
            count = int(row["c"]) if row else 0
            scored.append((count, -index, candidate))
        best = max(scored)
        if best[0] > 0:
            return best[2]

    # Then prefer any finance/catalog row that exists.
    for candidate in candidates:
        if "club_finances" in tables:
            row = conn.execute(
                "SELECT club FROM club_finances WHERE club=? COLLATE NOCASE LIMIT 1",
                (candidate,),
            ).fetchone()
            if row:
                return str(row["club"])
        if "league_teams" in tables:
            row = conn.execute(
                "SELECT name FROM league_teams WHERE name=? COLLATE NOCASE LIMIT 1",
                (candidate,),
            ).fetchone()
            if row:
                return str(row["name"])

    return canonical


def _player_dict(row: sqlite3.Row) -> dict:
    keys = set(row.keys())
    player_id = (
        int(row["id"])
        if "id" in keys and row["id"] is not None
        else None
    )
    return {
        "id": player_id,
        "code": f"AJAP-{player_id:06d}" if player_id is not None else None,
        "name": row["name"] if "name" in keys else row["player"],
        "position": row["position"] if "position" in keys else None,
        "club": row["club"] if "club" in keys else None,
        "ovr": (
            int(row["rating"])
            if "rating" in keys and row["rating"] is not None
            else None
        ),
        "market_value": (
            int(row["min_sale_value"])
            if "min_sale_value" in keys and row["min_sale_value"] is not None
            else None
        ),
    }


def status_payload(conn: sqlite3.Connection) -> dict:
    tables = _tables(conn)
    market_open = False
    updated_at = None
    if "market_state" in tables:
        row = conn.execute(
            "SELECT * FROM market_state WHERE id=1 LIMIT 1"
        ).fetchone()
        if row:
            market_open = bool(row["is_open"])
            updated_at = (
                row["updated_at"]
                if "updated_at" in row.keys()
                else None
            )

    season = None
    if "seasons" in tables:
        row = conn.execute(
            """
            SELECT id, name
            FROM seasons
            WHERE active=1
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if row:
            season = {"id": int(row["id"]), "name": row["name"]}

    return {
        "market_open": market_open,
        "market_updated_at": updated_at,
        "season": season,
    }


def clubs_payload(conn: sqlite3.Connection) -> list[dict]:
    """Expose only the canonical live club catalog used by Discord."""
    tables = _tables(conn)
    result = []

    for canonical_name in _live_mobile_club_names(conn):
        db_name = _resolve_db_club_name(conn, canonical_name)

        balance = None
        if "club_finances" in tables:
            row = conn.execute(
                """
                SELECT balance
                FROM club_finances
                WHERE club=? COLLATE NOCASE
                LIMIT 1
                """,
                (db_name,),
            ).fetchone()
            balance = int(row["balance"]) if row else 0

        roster_count = 0
        if "roster_players" in tables:
            roster_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM roster_players
                    WHERE club=? COLLATE NOCASE
                    """,
                    (db_name,),
                ).fetchone()["c"]
            )

        result.append(
            {
                "name": canonical_name,
                "balance": balance,
                "roster_count": roster_count,
            }
        )

    return result


def roster_payload(conn: sqlite3.Connection, club: str) -> list[dict]:
    if "roster_players" not in _tables(conn):
        return []

    # Only resolve aliases for clubs present in the live mobile catalog.
    canonical = next(
        (
            name
            for name in _live_mobile_club_names(conn)
            if name.casefold() == str(club or "").strip().casefold()
        ),
        str(club or "").strip(),
    )
    db_club = _resolve_db_club_name(conn, canonical)

    cols = _columns(conn, "roster_players")
    rating = "rating" if "rating" in cols else "NULL AS rating"
    value = (
        "min_sale_value"
        if "min_sale_value" in cols
        else "NULL AS min_sale_value"
    )
    rows = conn.execute(
        f"""
        SELECT id, name, position, club, {rating}, {value}
        FROM roster_players
        WHERE club=? COLLATE NOCASE
        ORDER BY COALESCE(rating,-1) DESC, name COLLATE NOCASE
        """,
        (db_club,),
    ).fetchall()
    return [_player_dict(row) for row in rows]


def market_payload(conn: sqlite3.Connection) -> list[dict]:
    tables = _tables(conn)
    if "publications" not in tables:
        return []

    pub_cols = _columns(conn, "publications")
    roster_cols = (
        _columns(conn, "roster_players")
        if "roster_players" in tables
        else set()
    )
    operation = (
        "p.operation_type"
        if "operation_type" in pub_cols
        else "'TRANSFERENCIA' AS operation_type"
    )
    rating = (
        "r.rating"
        if "rating" in roster_cols
        else "NULL AS rating"
    )
    value = (
        "r.min_sale_value"
        if "min_sale_value" in roster_cols
        else "NULL AS min_sale_value"
    )
    join = (
        "LEFT JOIN roster_players r ON r.name=p.player COLLATE NOCASE"
        if "roster_players" in tables
        else ""
    )
    rows = conn.execute(
        f"""
        SELECT p.id AS publication_id, p.player, p.position, p.club,
               p.price, p.detail, {operation}, {rating}, {value}
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
                "ovr": (
                    int(row["rating"])
                    if "rating" in keys and row["rating"] is not None
                    else None
                ),
                "market_value": (
                    int(row["min_sale_value"])
                    if "min_sale_value" in keys
                    and row["min_sale_value"] is not None
                    else None
                ),
                "is_free_agent": (
                    operation_type.upper() == "JUGADOR LIBRE"
                    or str(row["club"] or "").casefold()
                    == FREE_AGENT_CLUB.casefold()
                ),
            }
        )
    return result


def free_agents_payload(conn: sqlite3.Connection) -> list[dict]:
    return [
        item
        for item in market_payload(conn)
        if item["is_free_agent"]
    ]


def snapshot_payload(conn: sqlite3.Connection) -> dict:
    status = status_payload(conn)
    clubs = clubs_payload(conn)
    market = market_payload(conn)
    return {
        "read_only": True,
        "status": status,
        "clubs": clubs,
        "market": market,
        "free_agents": [
            item for item in market if item["is_free_agent"]
        ],
    }


class MobileReadHandler(BaseHTTPRequestHandler):
    server_version = "AJPA-Mobile-ReadAPI/0.2"

    def _json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
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
        self._json(
            {
                "error": "read_only",
                "message": "La API móvil todavía es solo lectura.",
            },
            HTTPStatus.METHOD_NOT_ALLOWED,
        )

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
                self._json(
                    {
                        "ok": True,
                        "service": "ajpa-mobile-read-api",
                        "read_only": True,
                    }
                )
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
                    self._json(
                        {"free_agents": free_agents_payload(conn)}
                    )
                    return
                if path == "/api/v1/snapshot":
                    self._json(snapshot_payload(conn))
                    return

                prefix = "/api/v1/clubs/"
                suffix = "/roster"
                if path.startswith(prefix) and path.endswith(suffix):
                    club = unquote(
                        path[len(prefix) : -len(suffix)]
                    ).strip("/")
                    if not club:
                        self._json(
                            {"error": "club_required"},
                            HTTPStatus.BAD_REQUEST,
                        )
                        return
                    self._json(
                        {
                            "club": club,
                            "players": roster_payload(conn, club),
                        }
                    )
                    return

            self._json(
                {"error": "not_found"},
                HTTPStatus.NOT_FOUND,
            )
        except FileNotFoundError as exc:
            self._json(
                {
                    "error": "database_not_found",
                    "message": str(exc),
                },
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            print(
                "AJPA mobile read API error: "
                f"{type(exc).__name__}: {exc}"
            )
            self._json(
                {"error": "internal_error"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, fmt, *args):
        print("AJPA mobile API:", fmt % args)


def start_mobile_read_api() -> ThreadingHTTPServer | None:
    enabled = (
        os.getenv("AJPA_MOBILE_API_ENABLED") or "0"
    ).strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        print(
            "AJPA mobile read API disabled "
            "(AJPA_MOBILE_API_ENABLED != 1)"
        )
        return None

    host = (
        os.getenv("AJPA_MOBILE_API_HOST") or "0.0.0.0"
    ).strip()
    port = int(
        os.getenv("PORT")
        or os.getenv("AJPA_MOBILE_API_PORT")
        or "8080"
    )
    server = ThreadingHTTPServer(
        (host, port),
        MobileReadHandler,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        name="ajpa-mobile-read-api",
        daemon=True,
    )
    thread.start()
    print(
        f"AJPA mobile read API listening on {host}:{port} "
        "• SQLite mode=ro • canonical JSON club catalog"
    )
    return server
