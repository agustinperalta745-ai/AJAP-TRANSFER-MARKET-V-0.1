"""Public club profiles + Staff titles/stars/prizes for AJPA Mobile.

The public profile combines the existing club finances, roster, market and
transfer history. Staff can maintain a club's honours and manually decide which
important titles grant stars. Prize payments credit the real club budget and
write a PREMIO entry into treasury_transactions so Discord and Mobile Treasury
show the same income as "Ingresos por premios".
"""

from __future__ import annotations

import os
import sqlite3
from http import HTTPStatus
from urllib.parse import unquote, urlparse

import mobile_parity_api_patch
import mobile_read_api
import mobile_staff_api_patch
import mobile_write_api


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS club_profile_meta (
            club TEXT PRIMARY KEY COLLATE NOCASE,
            stars INTEGER NOT NULL DEFAULT 0,
            updated_by INTEGER,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS club_titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club TEXT NOT NULL COLLATE NOCASE,
            title TEXT NOT NULL,
            important INTEGER NOT NULL DEFAULT 0,
            awarded_by INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(club, title)
        );

        CREATE TABLE IF NOT EXISTS club_prize_awards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club TEXT NOT NULL COLLATE NOCASE,
            prize TEXT NOT NULL,
            amount INTEGER NOT NULL,
            season_id INTEGER,
            staff_user_id INTEGER NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS treasury_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            club TEXT NOT NULL COLLATE NOCASE,
            season_id INTEGER,
            direction TEXT NOT NULL,
            category TEXT NOT NULL,
            amount INTEGER NOT NULL,
            player_id INTEGER,
            player TEXT,
            counterparty TEXT,
            reference_type TEXT,
            reference_id INTEGER,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(club, direction, category, reference_type, reference_id, season_id)
        );
        """
    )


def _canonical_club(conn: sqlite3.Connection, requested: str) -> str:
    raw = str(requested or "").strip()
    if not raw:
        raise mobile_write_api.ApiFailure("Elegí un equipo.")
    for club in mobile_read_api._live_mobile_club_names(conn):
        if club.casefold() == raw.casefold():
            return club
    raise mobile_write_api.ApiFailure("Ese equipo no existe en AJPA.", HTTPStatus.NOT_FOUND)


def _owner_row(conn: sqlite3.Connection, canonical: str):
    if "clubs" not in _tables(conn):
        return None
    db_name = mobile_read_api._resolve_db_club_name(conn, canonical)
    return conn.execute(
        "SELECT user_id, name FROM clubs WHERE name=? COLLATE NOCASE AND user_id IS NOT NULL LIMIT 1",
        (db_name,),
    ).fetchone()


def _cached_discord_name(user_id: int | None, club: str) -> str | None:
    if not user_id:
        return None
    try:
        import run_bot

        runtime = getattr(run_bot, "runtime", None)
        bot = getattr(runtime, "bot", None)
        raw_guild = (
            os.getenv("AJPA_MOBILE_GUILD_ID")
            or os.getenv("DISCORD_GUILD_ID")
            or ""
        ).strip()
        guild = bot.get_guild(int(raw_guild)) if bot and raw_guild else None
        member = guild.get_member(int(user_id)) if guild else None
        if member:
            label = str(member.display_name or member.name or "").strip()
            suffix = f" | {club}"
            if label.casefold().endswith(suffix.casefold()):
                label = label[: -len(suffix)].rstrip()
            if label:
                return label
    except Exception:
        pass
    return None


def _stored_discord_name(conn: sqlite3.Connection, user_id: int | None) -> str | None:
    if not user_id or "discord_nickname_state" not in _tables(conn):
        return None
    cols = mobile_read_api._columns(conn, "discord_nickname_state")
    if "original_nick" not in cols:
        return None
    row = conn.execute(
        "SELECT original_nick FROM discord_nickname_state WHERE user_id=? ORDER BY guild_id DESC LIMIT 1",
        (int(user_id),),
    ).fetchone()
    if row and str(row["original_nick"] or "").strip():
        return str(row["original_nick"]).strip()
    return None


def _manager_payload(conn: sqlite3.Connection, canonical: str) -> dict:
    row = _owner_row(conn, canonical)
    if not row:
        return {"user_id": None, "name": "Sin DT asignado"}
    user_id = int(row["user_id"])
    name = _cached_discord_name(user_id, canonical) or _stored_discord_name(conn, user_id)
    return {
        "user_id": str(user_id),
        "name": name or f"Discord · {user_id}",
    }


def _titles(conn: sqlite3.Connection, club: str) -> list[dict]:
    if "club_titles" not in _tables(conn):
        return []
    rows = conn.execute(
        """
        SELECT id, title, important, created_at
        FROM club_titles
        WHERE club=? COLLATE NOCASE
        ORDER BY id DESC
        """,
        (club,),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "title": str(row["title"]),
            "important": bool(row["important"]),
            "created_at": str(row["created_at"] or ""),
        }
        for row in rows
    ]


def _stars(conn: sqlite3.Connection, club: str) -> int:
    if "club_profile_meta" not in _tables(conn):
        return 0
    row = conn.execute(
        "SELECT stars FROM club_profile_meta WHERE club=? COLLATE NOCASE LIMIT 1",
        (club,),
    ).fetchone()
    return max(0, int(row["stars"] if row else 0))


def _summary_for(conn: sqlite3.Connection, canonical: str) -> dict:
    db_name = mobile_read_api._resolve_db_club_name(conn, canonical)
    balance = None
    roster_count = 0
    tables = _tables(conn)
    if "club_finances" in tables:
        row = conn.execute(
            "SELECT balance FROM club_finances WHERE club=? COLLATE NOCASE LIMIT 1",
            (db_name,),
        ).fetchone()
        balance = int(row["balance"] if row else 0)
    if "roster_players" in tables:
        roster_count = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM roster_players WHERE club=? COLLATE NOCASE",
                (db_name,),
            ).fetchone()["n"]
        )
    titles = _titles(conn, canonical)
    return {
        "club": canonical,
        "manager": _manager_payload(conn, canonical),
        "balance": balance,
        "roster_count": roster_count,
        "titles_count": len(titles),
        "stars": _stars(conn, canonical),
    }


def profiles_payload(conn: sqlite3.Connection) -> dict:
    clubs = [
        _summary_for(conn, club)
        for club in mobile_read_api._live_mobile_club_names(conn)
    ]
    return {"clubs": clubs}


def club_profile_payload(conn: sqlite3.Connection, requested: str) -> dict:
    club = _canonical_club(conn, requested)
    summary = _summary_for(conn, club)
    roster = mobile_read_api.roster_payload(conn, club)
    squad_value = sum(int(player.get("market_value") or 0) for player in roster)

    market = [
        item
        for item in mobile_read_api.market_payload(conn)
        if str(item.get("club") or "").casefold() == club.casefold()
    ]

    history = mobile_parity_api_patch.history_payload(conn, 200).get("items", [])
    movements = [
        item
        for item in history
        if str(item.get("seller") or "").casefold() == club.casefold()
        or str(item.get("buyer") or "").casefold() == club.casefold()
    ][:30]

    prizes = []
    if "club_prize_awards" in _tables(conn):
        rows = conn.execute(
            """
            SELECT id, prize, amount, season_id, created_at
            FROM club_prize_awards
            WHERE club=? COLLATE NOCASE
            ORDER BY id DESC LIMIT 20
            """,
            (club,),
        ).fetchall()
        prizes = [
            {
                "id": int(row["id"]),
                "prize": str(row["prize"]),
                "amount": int(row["amount"]),
                "season_id": int(row["season_id"]) if row["season_id"] is not None else None,
                "created_at": str(row["created_at"] or ""),
            }
            for row in rows
        ]

    return {
        **summary,
        "squad_value": squad_value,
        "titles": _titles(conn, club),
        "roster": roster,
        "market": market,
        "movements": movements,
        "prizes": prizes,
    }


def _active_season_id(conn: sqlite3.Connection) -> int | None:
    if "seasons" not in _tables(conn):
        return None
    row = conn.execute(
        "SELECT id FROM seasons WHERE active=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def _staff_add_title(conn: sqlite3.Connection, session: dict, payload: dict) -> dict:
    ensure_schema(conn)
    club = _canonical_club(conn, payload.get("club"))
    title = " ".join(str(payload.get("title") or "").strip().split())
    if len(title) < 2:
        raise mobile_write_api.ApiFailure("Escribí el nombre del título.")
    if len(title) > 100:
        raise mobile_write_api.ApiFailure("El nombre del título es demasiado largo.")
    important = bool(payload.get("important"))
    try:
        cursor = conn.execute(
            """
            INSERT INTO club_titles (club, title, important, awarded_by)
            VALUES (?, ?, ?, ?)
            """,
            (club, title, 1 if important else 0, int(session["user_id"])),
        )
    except sqlite3.IntegrityError:
        raise mobile_write_api.ApiFailure("Ese título ya figura en el perfil del equipo.")

    if important:
        conn.execute(
            """
            INSERT INTO club_profile_meta (club, stars, updated_by, updated_at)
            VALUES (?, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(club) DO UPDATE SET
                stars=club_profile_meta.stars + 1,
                updated_by=excluded.updated_by,
                updated_at=CURRENT_TIMESTAMP
            """,
            (club, int(session["user_id"])),
        )
    else:
        conn.execute(
            "INSERT OR IGNORE INTO club_profile_meta (club, stars, updated_by) VALUES (?, 0, ?)",
            (club, int(session["user_id"])),
        )
    return {
        "ok": True,
        "title_id": int(cursor.lastrowid),
        "club": club,
        "title": title,
        "important": important,
        "stars": _stars(conn, club),
    }


def _staff_set_stars(conn: sqlite3.Connection, session: dict, payload: dict) -> dict:
    ensure_schema(conn)
    club = _canonical_club(conn, payload.get("club"))
    try:
        stars = int(payload.get("stars"))
    except (TypeError, ValueError):
        raise mobile_write_api.ApiFailure("Indicá una cantidad válida de estrellas.")
    if stars < 0 or stars > 30:
        raise mobile_write_api.ApiFailure("Las estrellas deben estar entre 0 y 30.")
    conn.execute(
        """
        INSERT INTO club_profile_meta (club, stars, updated_by, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(club) DO UPDATE SET
            stars=excluded.stars,
            updated_by=excluded.updated_by,
            updated_at=CURRENT_TIMESTAMP
        """,
        (club, stars, int(session["user_id"])),
    )
    return {"ok": True, "club": club, "stars": stars}


def _staff_delete_title(conn: sqlite3.Connection, session: dict, payload: dict) -> dict:
    ensure_schema(conn)
    title_id = payload.get("title_id")
    if not str(title_id or "").isdigit():
        raise mobile_write_api.ApiFailure("Título inválido.")
    row = conn.execute(
        "SELECT id, club, title, important FROM club_titles WHERE id=? LIMIT 1",
        (int(title_id),),
    ).fetchone()
    if not row:
        raise mobile_write_api.ApiFailure("Ese título ya no existe.", HTTPStatus.NOT_FOUND)
    conn.execute("DELETE FROM club_titles WHERE id=?", (int(title_id),))
    # Important titles normally grant a star, but Staff may have manually edited
    # the count afterwards. Never guess by subtracting here; the explicit stars
    # control remains the correction authority.
    return {"ok": True, "club": str(row["club"]), "title": str(row["title"])}


def _staff_pay_prize(conn: sqlite3.Connection, session: dict, payload: dict) -> dict:
    ensure_schema(conn)
    club = _canonical_club(conn, payload.get("club"))
    prize = " ".join(str(payload.get("prize") or "").strip().split())
    if len(prize) < 2:
        raise mobile_write_api.ApiFailure("Escribí qué premio se está pagando.")
    if len(prize) > 120:
        raise mobile_write_api.ApiFailure("El nombre del premio es demasiado largo.")
    try:
        amount = int(payload.get("amount"))
    except (TypeError, ValueError):
        raise mobile_write_api.ApiFailure("Escribí un monto válido mayor a cero.")
    if amount <= 0:
        raise mobile_write_api.ApiFailure("El monto del premio debe ser mayor a cero.")

    db_club = mobile_read_api._resolve_db_club_name(conn, club)
    conn.execute(
        "INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)",
        (db_club,),
    )
    row = conn.execute(
        "SELECT balance FROM club_finances WHERE club=? COLLATE NOCASE LIMIT 1",
        (db_club,),
    ).fetchone()
    before = int(row["balance"] if row else 0)
    after = before + amount
    season_id = _active_season_id(conn)

    award = conn.execute(
        """
        INSERT INTO club_prize_awards (club, prize, amount, season_id, staff_user_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (club, prize, amount, season_id, int(session["user_id"])),
    )
    award_id = int(award.lastrowid)

    conn.execute(
        "UPDATE club_finances SET balance=?, updated_at=CURRENT_TIMESTAMP WHERE club=? COLLATE NOCASE",
        (after, db_club),
    )
    conn.execute(
        """
        INSERT INTO treasury_transactions
        (club, season_id, direction, category, amount, player_id, player,
         counterparty, reference_type, reference_id, description)
        VALUES (?, ?, 'INGRESO', 'PREMIO', ?, NULL, NULL,
                'Administración AJPA', 'PRIZE', ?, ?)
        """,
        (
            club,
            season_id,
            amount,
            award_id,
            f"Ingresos por premios · {prize}",
        ),
    )
    return {
        "ok": True,
        "award_id": award_id,
        "club": club,
        "prize": prize,
        "amount": amount,
        "balance_before": before,
        "balance_after": after,
    }


def treasury_payload(conn: sqlite3.Connection, headers) -> dict:
    ensure_schema(conn)
    session = mobile_write_api._session(headers, conn)
    club = mobile_write_api._require_club(conn, session)
    db_club = mobile_read_api._resolve_db_club_name(conn, club)
    row = conn.execute(
        "SELECT balance FROM club_finances WHERE club=? COLLATE NOCASE LIMIT 1",
        (db_club,),
    ).fetchone() if "club_finances" in _tables(conn) else None
    balance = int(row["balance"] if row else 0)

    items: list[dict] = []
    if "treasury_transactions" in _tables(conn):
        rows = conn.execute(
            """
            SELECT id, direction, category, amount, player, counterparty,
                   description, created_at
            FROM treasury_transactions
            WHERE club=? COLLATE NOCASE
            ORDER BY created_at DESC, id DESC
            LIMIT 100
            """,
            (club,),
        ).fetchall()
        for item in rows:
            category = str(item["category"] or "MOVIMIENTO")
            items.append({
                "id": f"treasury:{int(item['id'])}",
                "direction": str(item["direction"] or ""),
                "category": category,
                "category_label": "Ingresos por premios" if category == "PREMIO" else category.replace("_", " ").title(),
                "amount": int(item["amount"] or 0),
                "player": str(item["player"] or "") or None,
                "counterparty": str(item["counterparty"] or "") or None,
                "description": str(item["description"] or ""),
                "created_at": str(item["created_at"] or ""),
            })

    if "finance_adjustments" in _tables(conn):
        rows = conn.execute(
            """
            SELECT id, delta, created_at
            FROM finance_adjustments
            WHERE club=? COLLATE NOCASE
            ORDER BY created_at DESC, id DESC
            LIMIT 100
            """,
            (db_club,),
        ).fetchall()
        for item in rows:
            delta = int(item["delta"] or 0)
            items.append({
                "id": f"adjustment:{int(item['id'])}",
                "direction": "INGRESO" if delta >= 0 else "EGRESO",
                "category": "AJUSTE_ADMIN",
                "category_label": "Ajuste administrativo",
                "amount": abs(delta),
                "player": None,
                "counterparty": "Administración AJPA",
                "description": "Ajuste de presupuesto realizado por Staff",
                "created_at": str(item["created_at"] or ""),
            })

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"club": club, "balance": balance, "items": items[:100]}


def apply_mobile_club_profiles_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_club_profiles_api_patch", False):
        return

    try:
        with mobile_write_api.write_db() as conn:
            ensure_schema(conn)
            conn.commit()
    except Exception as exc:
        print(f"AJPA Mobile club profiles schema warning: {type(exc).__name__}: {exc}")

    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/api/v1/clubs/profiles":
                with mobile_read_api.readonly_db() as conn:
                    self._json(profiles_payload(conn))
                return
            if path.startswith("/api/v1/clubs/") and path.endswith("/profile"):
                encoded = path[len("/api/v1/clubs/") : -len("/profile")].strip("/")
                with mobile_read_api.readonly_db() as conn:
                    self._json(club_profile_payload(conn, unquote(encoded)))
                return
            if path == "/api/v1/my/treasury":
                with mobile_write_api.write_db() as conn:
                    self._json(treasury_payload(conn, self.headers))
                return
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
            return
        except Exception as exc:
            print(f"AJPA Mobile club profile GET error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudo cargar el perfil del equipo."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        return original_get(self)

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        actions = {
            "/api/v1/admin/clubs/profile/title": _staff_add_title,
            "/api/v1/admin/clubs/profile/stars": _staff_set_stars,
            "/api/v1/admin/clubs/profile/title/delete": _staff_delete_title,
            "/api/v1/admin/economy/prize": _staff_pay_prize,
        }
        action = actions.get(path)
        if action is None:
            return original_post(self)
        conn = None
        try:
            payload = mobile_write_api._read_json(self)
            conn = mobile_write_api.write_db()
            ensure_schema(conn)
            session = mobile_staff_api_patch._staff_session(self.headers, conn)
            conn.execute("BEGIN IMMEDIATE")
            result = action(conn, session, payload)
            conn.commit()
            self._json(result)
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
            print(f"AJPA Mobile club profile POST error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudo completar la operación."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        finally:
            if conn is not None:
                conn.close()

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_club_profiles_api_patch = True
    print("AJPA Mobile: perfiles públicos + títulos/estrellas + premios Staff activos")
