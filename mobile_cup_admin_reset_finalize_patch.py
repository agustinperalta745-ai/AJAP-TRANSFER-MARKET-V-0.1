"""Staff lifecycle controls for AJPA Champions/Europa editions.

Adds explicit, safe actions for the mobile cup center:
- reset an edition back to a clean DRAFT (seeds + bracket + test results removed),
- finalize Champions or Europa independently once its final has a winner,
- queue a persistent Radio Pasillo announcement for each finalized competition.

The existing tournament engine remains authoritative for seeding, bracket propagation
and score validation. This layer only manages lifecycle state around it.
"""

from __future__ import annotations

import re
import sqlite3
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_cup_tournaments_api_patch as cups
import mobile_read_api
import mobile_write_api

_EVENT_TABLE = "radio_pasillo_cup_final_events"


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
    except Exception:
        return set()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    cups.ensure_schema(conn)
    cols = _columns(conn, "cup_tournament_editions")
    if "champions_finished_at" not in cols:
        conn.execute("ALTER TABLE cup_tournament_editions ADD COLUMN champions_finished_at DATETIME")
    if "europa_finished_at" not in cols:
        conn.execute("ALTER TABLE cup_tournament_editions ADD COLUMN europa_finished_at DATETIME")
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_EVENT_TABLE} (
            edition_id INTEGER NOT NULL,
            competition TEXT NOT NULL,
            season_number INTEGER NOT NULL,
            champion TEXT NOT NULL,
            guild_id INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            channel_id INTEGER,
            discord_message_id INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            posted_at DATETIME,
            PRIMARY KEY (edition_id, competition)
        )
        """
    )


def _bootstrap() -> None:
    try:
        with mobile_write_api.write_db() as conn:
            _ensure_schema(conn)
            conn.commit()
    except Exception as exc:
        print(f"AJPA cup admin schema warning: {type(exc).__name__}: {exc}")


def _competition_meta(competition: str) -> tuple[str, str, str]:
    key = str(competition or "").strip().lower()
    if key == cups.CHAMPIONS:
        return "champions_champion", "champions_finished_at", "Champions AJPA"
    if key == cups.EUROPA:
        return "europa_champion", "europa_finished_at", "Europa AJPA"
    raise mobile_write_api.ApiFailure("Competencia inválida.")


def reset_edition(conn: sqlite3.Connection, edition_id: int) -> dict:
    edition = cups._edition(conn, int(edition_id))
    if not edition:
        raise mobile_write_api.ApiFailure("La edición no existe.", HTTPStatus.NOT_FOUND)

    conn.execute("DELETE FROM cup_matches WHERE edition_id=?", (int(edition_id),))
    conn.execute("DELETE FROM cup_seed_slots WHERE edition_id=?", (int(edition_id),))
    conn.execute(f"DELETE FROM {_EVENT_TABLE} WHERE edition_id=?", (int(edition_id),))
    conn.execute(
        """UPDATE cup_tournament_editions
           SET status='DRAFT', started_at=NULL, finished_at=NULL,
               champions_champion=NULL, europa_champion=NULL,
               champions_finished_at=NULL, europa_finished_at=NULL
           WHERE id=?""",
        (int(edition_id),),
    )
    return {
        "ok": True,
        "edition_id": int(edition_id),
        "status": "DRAFT",
        "message": "Copas reiniciadas. Se borraron preclasificación, cruces y resultados de esta edición.",
    }


def finalize_competition(conn: sqlite3.Connection, edition_id: int, competition: str) -> dict:
    edition = cups._edition(conn, int(edition_id))
    if not edition:
        raise mobile_write_api.ApiFailure("La edición no existe.", HTTPStatus.NOT_FOUND)

    champion_field, finished_field, display_name = _competition_meta(competition)
    keys = set(edition.keys())
    champion = str(edition[champion_field] or "").strip()
    if not champion:
        raise mobile_write_api.ApiFailure(
            f"Todavía no hay campeón de {display_name}. Cargá primero el resultado de la final.",
            HTTPStatus.CONFLICT,
        )

    current_finished = edition[finished_field] if finished_field in keys else None
    if current_finished:
        return {
            "ok": True,
            "edition_id": int(edition_id),
            "competition": str(competition),
            "champion": champion,
            "already_finished": True,
        }

    conn.execute(
        f"UPDATE cup_tournament_editions SET {finished_field}=CURRENT_TIMESTAMP WHERE id=?",
        (int(edition_id),),
    )
    refreshed = cups._edition(conn, int(edition_id))
    refreshed_keys = set(refreshed.keys()) if refreshed else set()
    champions_done = bool(refreshed and "champions_finished_at" in refreshed_keys and refreshed["champions_finished_at"])
    europa_done = bool(refreshed and "europa_finished_at" in refreshed_keys and refreshed["europa_finished_at"])
    if champions_done and europa_done:
        conn.execute(
            "UPDATE cup_tournament_editions SET status='FINISHED',finished_at=COALESCE(finished_at,CURRENT_TIMESTAMP) WHERE id=?",
            (int(edition_id),),
        )
    else:
        # A final result may have made the legacy engine mark the combined edition
        # FINISHED. Keep it ACTIVE until Staff explicitly closes both competitions.
        conn.execute(
            "UPDATE cup_tournament_editions SET status='ACTIVE',finished_at=NULL WHERE id=?",
            (int(edition_id),),
        )

    conn.execute(
        f"""INSERT INTO {_EVENT_TABLE}
               (edition_id,competition,season_number,champion,guild_id,status,created_at)
           VALUES(?,?,?,?,0,'pending',CURRENT_TIMESTAMP)
           ON CONFLICT(edition_id,competition) DO UPDATE SET
               season_number=excluded.season_number,
               champion=excluded.champion,
               guild_id=0,
               status='pending',
               channel_id=NULL,
               discord_message_id=NULL,
               created_at=CURRENT_TIMESTAMP,
               posted_at=NULL""",
        (int(edition_id), str(competition), int(edition["season_number"]), champion),
    )
    return {
        "ok": True,
        "edition_id": int(edition_id),
        "competition": str(competition),
        "champion": champion,
        "status": "FINISHED" if champions_done and europa_done else "ACTIVE",
    }


def _augment_payload(conn: sqlite3.Connection, payload: dict) -> dict:
    edition_payload = payload.get("edition") if isinstance(payload, dict) else None
    if not isinstance(edition_payload, dict) or edition_payload.get("id") is None:
        return payload
    _ensure_schema(conn)
    row = conn.execute(
        "SELECT champions_finished_at,europa_finished_at FROM cup_tournament_editions WHERE id=? LIMIT 1",
        (int(edition_payload["id"]),),
    ).fetchone()
    if row:
        edition_payload["champions_finished_at"] = str(row["champions_finished_at"] or "") or None
        edition_payload["europa_finished_at"] = str(row["europa_finished_at"] or "") or None
    return payload


def apply_mobile_cup_admin_reset_finalize_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_cup_admin_reset_finalize_patch", False):
        return
    _bootstrap()
    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/cups":
            return original_get(self)
        try:
            with mobile_write_api.write_db() as conn:
                _ensure_schema(conn)
                payload = _augment_payload(conn, cups.public_payload(conn))
                conn.commit()
                self._json(payload)
        except Exception as exc:
            print(f"AJPA cup admin GET error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudieron cargar las copas."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        reset_match = re.fullmatch(r"/api/v1/cups/(\d+)/reset", path)
        finish_match = re.fullmatch(r"/api/v1/cups/(\d+)/finish/(champions|europa)", path)
        if not reset_match and not finish_match:
            return original_post(self)
        conn = None
        try:
            # Consume a JSON body for parity with the mobile transport; empty {} is valid.
            mobile_write_api._read_json(self)
            with mobile_write_api.write_db() as conn:
                _ensure_schema(conn)
                cups._staff_session(self.headers, conn)
                if reset_match:
                    result = reset_edition(conn, int(reset_match.group(1)))
                else:
                    result = finalize_competition(conn, int(finish_match.group(1)), finish_match.group(2))
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
            print(f"AJPA cup admin POST error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo actualizar la copa."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_cup_admin_reset_finalize_patch = True
    print("AJPA cups: reinicio + cierre explícito Champions/Europa habilitados")
