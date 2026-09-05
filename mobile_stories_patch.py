"""Instagram-style 24h team stories for AJPA Mobile.

Stories belong to the authenticated Discord user's assigned club. The client can
never choose another club identity. Photo + caption are moderated before any
story is persisted; moderation fails closed when it cannot run.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_read_api
import mobile_write_api

STORY_TTL_SECONDS = 24 * 60 * 60
MAX_ACTIVE_STORIES_PER_CLUB = 10
MAX_CAPTION_CHARS = 250
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 3 * 1024 * 1024
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}


class StoryModerationUnavailable(Exception):
    pass


class StoryRejected(Exception):
    pass


def _ensure_story_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mobile_stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_user_id INTEGER NOT NULL,
            team TEXT NOT NULL,
            image_data_url TEXT NOT NULL,
            caption TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mobile_story_views (
            story_id INTEGER NOT NULL,
            discord_user_id INTEGER NOT NULL,
            viewed_at INTEGER NOT NULL,
            PRIMARY KEY (story_id, discord_user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_mobile_stories_expires
            ON mobile_stories(expires_at);
        CREATE INDEX IF NOT EXISTS idx_mobile_stories_team
            ON mobile_stories(team, expires_at);
        """
    )


def _purge_expired(conn: sqlite3.Connection, now: int | None = None) -> None:
    now = int(now or time.time())
    conn.execute(
        "DELETE FROM mobile_story_views WHERE story_id IN (SELECT id FROM mobile_stories WHERE expires_at<=?)",
        (now,),
    )
    conn.execute("DELETE FROM mobile_stories WHERE expires_at<=?", (now,))


def _read_story_json(handler) -> dict:
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except ValueError:
        raise mobile_write_api.ApiFailure("Solicitud inválida.")
    if length <= 0:
        return {}
    if length > MAX_REQUEST_BYTES:
        raise mobile_write_api.ApiFailure(
            "La imagen es demasiado pesada. Elegí una foto más liviana.",
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        )
    raw = handler.rfile.read(length)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise mobile_write_api.ApiFailure("No pude leer la historia.")
    if not isinstance(value, dict):
        raise mobile_write_api.ApiFailure("Formato de historia inválido.")
    return value


def _validate_image_data_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw.startswith("data:image/") or ";base64," not in raw:
        raise mobile_write_api.ApiFailure("La historia necesita una foto válida.")
    header, encoded = raw.split(",", 1)
    mime = header[5:].split(";", 1)[0].lower()
    if mime not in ALLOWED_IMAGE_MIMES:
        raise mobile_write_api.ApiFailure("Usá una imagen JPG, PNG o WEBP.")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise mobile_write_api.ApiFailure("No pude leer la imagen seleccionada.")
    if not decoded:
        raise mobile_write_api.ApiFailure("La imagen está vacía.")
    if len(decoded) > MAX_IMAGE_BYTES:
        raise mobile_write_api.ApiFailure(
            "La imagen supera 2 MB. Elegí una foto más liviana.",
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        )
    return raw


def _moderate_story(image_data_url: str, caption: str) -> None:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise StoryModerationUnavailable("OPENAI_API_KEY no configurada")

    moderation_input = [
        {
            "type": "image_url",
            "image_url": {"url": image_data_url},
        }
    ]
    if caption.strip():
        moderation_input.insert(0, {"type": "text", "text": caption.strip()})

    body = json.dumps(
        {
            "model": "omni-moderation-latest",
            "input": moderation_input,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/moderations",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise StoryModerationUnavailable(str(exc)) from exc

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not results:
        raise StoryModerationUnavailable("respuesta de moderación incompleta")
    if bool(results[0].get("flagged")):
        raise StoryRejected()


def _story_item(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "team": str(row["team"]),
        "image_data_url": str(row["image_data_url"]),
        "caption": str(row["caption"] or ""),
        "created_at": int(row["created_at"]),
        "expires_at": int(row["expires_at"]),
        "viewed": bool(row["viewed"]),
        "owner": bool(row["owner"]),
    }


def stories_payload(conn: sqlite3.Connection, session: dict) -> dict:
    _ensure_story_schema(conn)
    now = int(time.time())
    _purge_expired(conn, now)
    viewer_id = int(session["user_id"])
    own_team = mobile_write_api.mobile_auth.resolve_club_readonly(conn, viewer_id)
    rows = conn.execute(
        """
        SELECT s.*,
               CASE WHEN v.story_id IS NULL THEN 0 ELSE 1 END AS viewed,
               CASE WHEN s.discord_user_id=? THEN 1 ELSE 0 END AS owner
        FROM mobile_stories s
        LEFT JOIN mobile_story_views v
          ON v.story_id=s.id AND v.discord_user_id=?
        WHERE s.expires_at>?
        ORDER BY s.created_at ASC, s.id ASC
        """,
        (viewer_id, viewer_id, now),
    ).fetchall()
    return {
        "own_team": own_team,
        "server_time": now,
        "stories": [_story_item(row) for row in rows],
    }


def create_story(conn: sqlite3.Connection, session: dict, payload: dict) -> dict:
    _ensure_story_schema(conn)
    now = int(time.time())
    _purge_expired(conn, now)
    team = mobile_write_api._require_club(conn, session)
    caption = str(payload.get("caption") or "").strip()
    if len(caption) > MAX_CAPTION_CHARS:
        raise mobile_write_api.ApiFailure(
            f"El texto puede tener hasta {MAX_CAPTION_CHARS} caracteres."
        )
    image_data_url = _validate_image_data_url(payload.get("image_data_url"))

    active_count = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM mobile_stories WHERE team=? COLLATE NOCASE AND expires_at>?",
            (team, now),
        ).fetchone()["n"]
    )
    if active_count >= MAX_ACTIVE_STORIES_PER_CLUB:
        raise mobile_write_api.ApiFailure(
            f"{team} ya tiene {MAX_ACTIVE_STORIES_PER_CLUB} historias activas. Esperá a que venza una.",
            HTTPStatus.CONFLICT,
        )

    # Do not write anything until both image and caption pass moderation.
    _moderate_story(image_data_url, caption)

    cursor = conn.execute(
        """
        INSERT INTO mobile_stories
            (discord_user_id, team, image_data_url, caption, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (int(session["user_id"]), team, image_data_url, caption, now, now + STORY_TTL_SECONDS),
    )
    story_id = int(cursor.lastrowid)
    return {
        "ok": True,
        "story_id": story_id,
        "team": team,
        "created_at": now,
        "expires_at": now + STORY_TTL_SECONDS,
    }


def mark_story_viewed(conn: sqlite3.Connection, session: dict, story_id: int) -> dict:
    _ensure_story_schema(conn)
    now = int(time.time())
    row = conn.execute(
        "SELECT id FROM mobile_stories WHERE id=? AND expires_at>?",
        (int(story_id), now),
    ).fetchone()
    if not row:
        raise mobile_write_api.ApiFailure("La historia ya venció.", HTTPStatus.NOT_FOUND)
    conn.execute(
        """
        INSERT INTO mobile_story_views(story_id, discord_user_id, viewed_at)
        VALUES(?,?,?)
        ON CONFLICT(story_id, discord_user_id) DO UPDATE SET viewed_at=excluded.viewed_at
        """,
        (int(story_id), int(session["user_id"]), now),
    )
    return {"ok": True, "story_id": int(story_id)}


def delete_story(conn: sqlite3.Connection, session: dict, story_id: int) -> dict:
    _ensure_story_schema(conn)
    row = conn.execute(
        "SELECT discord_user_id FROM mobile_stories WHERE id=?",
        (int(story_id),),
    ).fetchone()
    if not row:
        raise mobile_write_api.ApiFailure("La historia ya no existe.", HTTPStatus.NOT_FOUND)
    if int(row["discord_user_id"]) != int(session["user_id"]) and not session.get("is_staff"):
        raise mobile_write_api.ApiFailure("No podés borrar esa historia.", HTTPStatus.FORBIDDEN)
    conn.execute("DELETE FROM mobile_story_views WHERE story_id=?", (int(story_id),))
    conn.execute("DELETE FROM mobile_stories WHERE id=?", (int(story_id),))
    return {"ok": True, "story_id": int(story_id)}


def _parts(path: str) -> list[str]:
    return [part for part in path.strip("/").split("/") if part]


def apply_mobile_stories_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_stories_patch", False):
        return

    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/stories":
            return original_get(self)
        try:
            with mobile_write_api.write_db() as conn:
                session = mobile_write_api._session(self.headers, conn)
                result = stories_payload(conn, session)
                conn.commit()
            self._json(result, HTTPStatus.OK)
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            print(f"AJPA stories read error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudieron cargar las historias."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        parts = _parts(path)
        is_create = path == "/api/v1/stories"
        is_view = len(parts) == 5 and parts[:3] == ["api", "v1", "stories"] and parts[3].isdigit() and parts[4] == "view"
        is_delete = len(parts) == 5 and parts[:3] == ["api", "v1", "stories"] and parts[3].isdigit() and parts[4] == "delete"
        if not (is_create or is_view or is_delete):
            return original_post(self)

        conn = None
        try:
            payload = _read_story_json(self)
            conn = mobile_write_api.write_db()
            mobile_write_api.ensure_schema(conn)
            session = mobile_write_api._session(self.headers, conn)
            if is_create:
                result = create_story(conn, session, payload)
                status = HTTPStatus.CREATED
            elif is_view:
                result = mark_story_viewed(conn, session, int(parts[3]))
                status = HTTPStatus.OK
            else:
                result = delete_story(conn, session, int(parts[3]))
                status = HTTPStatus.OK
            conn.commit()
            self._json(result, status)
        except StoryRejected:
            if conn is not None:
                conn.rollback()
            self._json(
                {
                    "error": "story_rejected",
                    "message": "Esta historia no se puede publicar porque el contenido no cumple las reglas de AJPA.",
                },
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        except StoryModerationUnavailable as exc:
            if conn is not None:
                conn.rollback()
            print(f"AJPA story moderation unavailable: {exc}")
            self._json(
                {
                    "error": "moderation_unavailable",
                    "message": "No pudimos verificar el contenido ahora. La historia no se publicó; intentá nuevamente.",
                },
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        except mobile_write_api.ApiFailure as exc:
            if conn is not None:
                conn.rollback()
            self._json({"error": "request", "message": exc.message}, exc.status)
        except sqlite3.IntegrityError as exc:
            if conn is not None:
                conn.rollback()
            print(f"AJPA stories integrity error: {exc}")
            self._json({"error": "conflict", "message": "La historia cambió mientras la procesábamos."}, HTTPStatus.CONFLICT)
        except Exception as exc:
            if conn is not None:
                conn.rollback()
            print(f"AJPA stories write error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo completar la historia."}, HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            if conn is not None:
                conn.close()

    handler.do_GET = get
    handler.do_POST = post
    handler._ajpa_mobile_stories_patch = True
    print("AJPA Mobile: historias de equipos 24h + vistas + moderación habilitadas")
