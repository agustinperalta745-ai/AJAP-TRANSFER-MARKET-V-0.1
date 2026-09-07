"""Per-competition GES configuration and authoritative seasonal synchronization.

Every playable AJPA competition owns its GES URLs. Finished competitions keep
those URLs and their data forever. The active competition is the only one that
can be changed by a manual Staff "GES actualizada" synchronization.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import threading
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

import competition_cycle as cycle
import league_ges_manual_sync_patch as ges
import mobile_read_api
import mobile_write_api

_RUNTIME = None
_BOT = None
_SEASON_SYNC_LOCK = threading.Lock()
_BOOT_LEAGUE_ID = str(ges.GES_LEAGUE_ID)
_BOOT_CLASSIFICATION_URL = str(ges.GES_CLASSIFICATION_URL)
_BOOT_SCORERS_URL = str(ges.GES_SCORERS_URL)
_BOOT_RESULTS_URL = (
    os.getenv("AJPA_GES_RESULTS_URL")
    or f"https://www.gesliga.com/CuadranteResultados.aspx?Liga={_BOOT_LEAGUE_ID}"
).strip()


def _ensure_config_schema(conn) -> None:
    cycle.ensure_schema(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS league_ges_competition_config (
            competition_id INTEGER PRIMARY KEY,
            competition_label TEXT NOT NULL,
            league_id TEXT NOT NULL,
            classification_url TEXT NOT NULL,
            results_url TEXT NOT NULL,
            scorers_url TEXT NOT NULL,
            updated_by INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()


def _guild_id() -> int:
    raw = (os.getenv("AJPA_MOBILE_GUILD_ID") or os.getenv("DISCORD_GUILD_ID") or "").strip()
    if raw.isdigit():
        return int(raw)
    if _BOT is not None:
        guilds = list(getattr(_BOT, "guilds", []) or [])
        if len(guilds) == 1:
            return int(guilds[0].id)
    raise mobile_write_api.ApiFailure(
        "AJPA Mobile no tiene servidor configurado.", HTTPStatus.SERVICE_UNAVAILABLE
    )


def _league_conn():
    if _RUNTIME is None:
        raise mobile_write_api.ApiFailure(
            "AJPA todavía está terminando de iniciar.", HTTPStatus.SERVICE_UNAVAILABLE
        )
    return ges.league.db(_RUNTIME, _guild_id())


def _active_edition(conn) -> tuple[int, str]:
    _ensure_config_schema(conn)
    cid = cycle.active_competition_id(conn)
    if cid is None:
        raise mobile_write_api.ApiFailure(
            "No hay una competencia activa. Iniciá la temporada o copa antes de configurar GES.",
            HTTPStatus.CONFLICT,
        )
    row = conn.execute(
        "SELECT label FROM competition_editions WHERE id=?", (int(cid),)
    ).fetchone()
    return int(cid), str(row["label"] if row else f"Competencia {cid}")


def _league_id_from_url(value: str) -> str | None:
    try:
        parsed = urlparse(value)
        query = parse_qs(parsed.query)
        for key, values in query.items():
            if key.casefold() == "liga" and values:
                raw = str(values[0]).strip()
                if raw:
                    return raw
    except Exception:
        return None
    return None


def _valid_url(value: str) -> str:
    value = str(value or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise mobile_write_api.ApiFailure(
            "Los tres enlaces de GES deben ser URLs completas http/https.", HTTPStatus.BAD_REQUEST
        )
    return value


def _has_any_saved_config(conn) -> bool:
    row = conn.execute("SELECT 1 FROM league_ges_competition_config LIMIT 1").fetchone()
    return bool(row)


def _config_row(conn, competition_id: int):
    return conn.execute(
        """SELECT competition_id,competition_label,league_id,classification_url,
                  results_url,scorers_url,updated_at
           FROM league_ges_competition_config WHERE competition_id=?""",
        (int(competition_id),),
    ).fetchone()


def _current_config_payload(conn) -> dict:
    cid, label = _active_edition(conn)
    row = _config_row(conn, cid)
    if row:
        return {
            "competition_id": int(row["competition_id"]),
            "competition_label": str(row["competition_label"]),
            "league_id": str(row["league_id"]),
            "ges_url": str(row["classification_url"]),
            "results_url": str(row["results_url"]),
            "scorers_url": str(row["scorers_url"]),
            "configured": True,
            "updated_at": str(row["updated_at"] or ""),
        }

    # First migration keeps the already-working current GES ready to save.
    # Once at least one edition was configured, a newly-created edition starts
    # blank so Staff cannot accidentally sync it against the previous season.
    if _has_any_saved_config(conn):
        ges_url = results_url = scorers_url = ""
        league_id = ""
    else:
        ges_url = _BOOT_CLASSIFICATION_URL
        results_url = _BOOT_RESULTS_URL
        scorers_url = _BOOT_SCORERS_URL
        league_id = _BOOT_LEAGUE_ID
    return {
        "competition_id": cid,
        "competition_label": label,
        "league_id": league_id,
        "ges_url": ges_url,
        "results_url": results_url,
        "scorers_url": scorers_url,
        "configured": False,
        "updated_at": "",
    }


def _save_current_config(conn, body: dict, user_id: int) -> dict:
    cid, label = _active_edition(conn)
    classification = _valid_url(body.get("ges_url"))
    results = _valid_url(body.get("results_url"))
    scorers = _valid_url(body.get("scorers_url"))
    ids = [v for v in (
        _league_id_from_url(classification),
        _league_id_from_url(results),
        _league_id_from_url(scorers),
    ) if v]
    if ids and any(value != ids[0] for value in ids[1:]):
        raise mobile_write_api.ApiFailure(
            "Los tres enlaces parecen pertenecer a ligas GES diferentes.", HTTPStatus.BAD_REQUEST
        )
    league_id = ids[0] if ids else str(body.get("league_id") or _BOOT_LEAGUE_ID).strip()
    conn.execute(
        """INSERT INTO league_ges_competition_config
           (competition_id,competition_label,league_id,classification_url,results_url,scorers_url,updated_by)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(competition_id) DO UPDATE SET
             competition_label=excluded.competition_label,
             league_id=excluded.league_id,
             classification_url=excluded.classification_url,
             results_url=excluded.results_url,
             scorers_url=excluded.scorers_url,
             updated_by=excluded.updated_by,
             updated_at=CURRENT_TIMESTAMP""",
        (cid, label, league_id, classification, results, scorers, int(user_id)),
    )
    conn.commit()
    return _current_config_payload(conn)


def _config_history(conn) -> list[dict]:
    _ensure_config_schema(conn)
    rows = conn.execute(
        """SELECT c.competition_id,c.competition_label,c.league_id,
                  c.classification_url,c.results_url,c.scorers_url,c.updated_at,
                  e.kind,e.season_number,e.status,e.ended_at
           FROM league_ges_competition_config c
           LEFT JOIN competition_editions e ON e.id=c.competition_id
           ORDER BY c.competition_id DESC"""
    ).fetchall()
    return [
        {
            "competition_id": int(row["competition_id"]),
            "competition_label": str(row["competition_label"]),
            "league_id": str(row["league_id"]),
            "ges_url": str(row["classification_url"]),
            "results_url": str(row["results_url"]),
            "scorers_url": str(row["scorers_url"]),
            "kind": str(row["kind"] or ""),
            "season_number": int(row["season_number"] or 0),
            "status": str(row["status"] or ""),
            "ended_at": str(row["ended_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }
        for row in rows
    ]


def _source_id(prefix: str, league_id: str, competition_id: int, *values: str) -> int:
    text = "|".join([prefix, league_id, str(competition_id), *[ges._norm(v) for v in values]])
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return -(int.from_bytes(digest[:7], "big") or 1)


def _competition_matches(conn, competition_id: int) -> list[dict]:
    cols = {str(row["name"]) for row in conn.execute("PRAGMA table_info(league_matches)")}
    if "competition_id" not in cols:
        return []
    rows = conn.execute(
        """SELECT id,home_team,away_team,home_goals,away_goals
           FROM league_matches WHERE competition_id=? ORDER BY id DESC""",
        (int(competition_id),),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "home_team": str(row["home_team"]),
            "away_team": str(row["away_team"]),
            "home_goals": int(row["home_goals"]),
            "away_goals": int(row["away_goals"]),
        }
        for row in rows
    ]


def _season_history_payload(conn) -> dict:
    _ensure_config_schema(conn)
    rows = conn.execute(
        """SELECT id,kind,season_number,label,status,started_at,ended_at,final_snapshot_json
           FROM competition_editions ORDER BY id DESC"""
    ).fetchall()
    editions = []
    for row in rows:
        cid = int(row["id"])
        raw = row["final_snapshot_json"]
        if raw:
            try:
                snapshot = json.loads(str(raw))
            except Exception:
                snapshot = {"standings": [], "scorers": []}
        else:
            try:
                snapshot = json.loads(cycle._snapshot(conn, cid))
            except Exception:
                snapshot = {"standings": [], "scorers": []}
        editions.append({
            "id": cid,
            "kind": str(row["kind"]),
            "season_number": int(row["season_number"]),
            "label": str(row["label"]),
            "status": str(row["status"]),
            "standings": list(snapshot.get("standings") or []),
            "scorers": list(snapshot.get("scorers") or []),
            "matches": _competition_matches(conn, cid),
        })
    return {"competitions": editions}


async def _seasonal_sync(runtime, bot, guild_id: int, staff_user_id: int | None = None) -> dict:
    if not _SEASON_SYNC_LOCK.acquire(blocking=False):
        raise RuntimeError("Ya hay una sincronización GES en curso.")
    try:
        conn = ges.league.db(runtime, int(guild_id))
        try:
            cfg = _current_config_payload(conn)
            cid = int(cfg["competition_id"])
            if not cfg.get("configured"):
                raise RuntimeError(
                    f"Primero guardá los tres enlaces GES de {cfg['competition_label']} en Administración."
                )
        finally:
            conn.close()

        league_id = str(cfg["league_id"])
        classification_url = str(cfg["ges_url"])
        results_url = str(cfg["results_url"])
        scorers_url = str(cfg["scorers_url"])

        # Keep Discord standings/scorer views pointed at the last confirmed sync.
        ges.GES_LEAGUE_ID = league_id
        ges.GES_CLASSIFICATION_URL = classification_url
        ges.GES_SCORERS_URL = scorers_url
        ges.GES_RESULTS_URL = results_url

        classification_html, results_html, scorers_html = await asyncio.gather(
            asyncio.to_thread(ges._fetch, classification_url),
            asyncio.to_thread(ges._fetch, results_url),
            asyncio.to_thread(ges._fetch, scorers_url),
        )
        standings, warnings_a = ges._parse_standings(ges._tables(classification_html))
        matches, warnings_b = ges._parse_matches(ges._tables(results_html))
        scorers, warnings_c = ges._parse_scorers(ges._tables(scorers_html))
        warnings = list(dict.fromkeys(warnings_a + warnings_b + warnings_c))

        conn = ges.league.db(runtime, int(guild_id))
        changed_sources: list[int] = []
        matches_new = 0
        matches_updated = 0
        try:
            ges._ensure_schema(conn)
            _ensure_config_schema(conn)
            active_cid = cycle.active_competition_id(conn)
            if active_cid != cid:
                raise RuntimeError("La competencia cambió durante la sincronización. Volvé a intentarlo.")

            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM league_ges_standings WHERE guild_id=? AND league_id=?",
                (int(guild_id), league_id),
            )
            for row in standings:
                conn.execute(
                    """INSERT INTO league_ges_standings
                       (guild_id,league_id,position,team,pts,pj,pg,pe,pp,gf,gc,dg)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (int(guild_id), league_id, row["position"], row["team"], row["pts"],
                     row["pj"], row["pg"], row["pe"], row["pp"], row["gf"], row["gc"], row["dg"]),
                )

            for item in matches:
                existing = conn.execute(
                    """SELECT id,source_message_id,home_goals,away_goals FROM league_matches
                       WHERE home_team=? AND away_team=? AND competition_id=?
                       ORDER BY id DESC LIMIT 1""",
                    (item["home_team"], item["away_team"], cid),
                ).fetchone()
                if existing:
                    source_id = int(existing["source_message_id"])
                    if (int(existing["home_goals"]) != item["home_goals"]
                            or int(existing["away_goals"]) != item["away_goals"]):
                        conn.execute(
                            "UPDATE league_matches SET home_goals=?,away_goals=?,confidence=1.0 WHERE id=?",
                            (item["home_goals"], item["away_goals"], int(existing["id"])),
                        )
                        matches_updated += 1
                        changed_sources.append(source_id)
                else:
                    source_id = _source_id(
                        "GES-MATCH", league_id, cid, item["home_team"], item["away_team"]
                    )
                    conn.execute(
                        """INSERT INTO league_matches
                           (source_message_id,source_channel_id,author_id,home_team,away_team,
                            home_goals,away_goals,confidence,competition_id)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (source_id, 0, int(staff_user_id or 0), item["home_team"], item["away_team"],
                         item["home_goals"], item["away_goals"], 1.0, cid),
                    )
                    matches_new += 1
                    changed_sources.append(source_id)

            conn.execute(
                "DELETE FROM league_ges_scorers WHERE guild_id=? AND league_id=?",
                (int(guild_id), league_id),
            )
            for row in scorers:
                conn.execute(
                    "INSERT INTO league_ges_scorers(guild_id,league_id,player,team,goals) VALUES(?,?,?,?,?)",
                    (int(guild_id), league_id, row["player"], row["team"] or "", row["goals"]),
                )

            # Mobile's active scorer table and competition archives use
            # league_goal_events. GES totals replace only the active edition.
            conn.execute("DELETE FROM league_goal_events WHERE competition_id=?", (cid,))
            for row in scorers:
                scorer_source = _source_id(
                    "GES-SCORER", league_id, cid, row["player"], row["team"] or ""
                )
                conn.execute(
                    """INSERT INTO league_goal_events
                       (source_message_id,player,team,goals,confidence,competition_id)
                       VALUES(?,?,?,?,1.0,?)""",
                    (scorer_source, row["player"], row["team"] or "", int(row["goals"]), cid),
                )

            conn.execute(
                """INSERT INTO league_ges_sync_runs
                   (guild_id,league_id,staff_user_id,standings_count,matches_new,matches_updated,
                    scorers_count,warning_count)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (int(guild_id), league_id, staff_user_id, len(standings), matches_new,
                 matches_updated, len(scorers), len(warnings)),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        warnings.extend(await ges._refresh_downstream(runtime, bot, int(guild_id), changed_sources))
        return {
            "ok": True,
            "league_id": league_id,
            "competition_id": cid,
            "competition_label": cfg["competition_label"],
            "standings": len(standings),
            "matches_read": len(matches),
            "matches_new": matches_new,
            "matches_updated": matches_updated,
            "scorers": len(scorers),
            "warnings": list(dict.fromkeys(warnings))[:40],
        }
    finally:
        _SEASON_SYNC_LOCK.release()


def _staff_session(headers) -> dict:
    with mobile_write_api.write_db() as conn:
        mobile_write_api.ensure_schema(conn)
        session = mobile_write_api._session(headers, conn)
        if not session.get("is_staff"):
            raise mobile_write_api.ApiFailure(
                "Esta herramienta es exclusiva para Staff.", HTTPStatus.FORBIDDEN
            )
        return session


def _install_api() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_season_ges_authority_api", False):
        return
    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path not in {"/api/v1/admin/ges-config", "/api/v1/league/seasons"}:
            return original_get(self)
        conn = None
        try:
            if path == "/api/v1/admin/ges-config":
                _staff_session(self.headers)
                conn = _league_conn()
                payload = _current_config_payload(conn)
                payload["history"] = _config_history(conn)
            else:
                conn = _league_conn()
                payload = _season_history_payload(conn)
            self._json(payload)
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            print(f"AJPA season GES GET error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "season_ges", "message": str(exc) or "No se pudo cargar la información."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        finally:
            if conn is not None:
                conn.close()

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/admin/ges-config":
            return original_post(self)
        conn = None
        try:
            session = _staff_session(self.headers)
            body = mobile_write_api._read_json(self)
            conn = _league_conn()
            payload = _save_current_config(conn, body, int(session["user_id"]))
            payload["ok"] = True
            payload["history"] = _config_history(conn)
            self._json(payload)
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"AJPA season GES POST error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "season_ges", "message": str(exc) or "No se pudieron guardar los enlaces."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        finally:
            if conn is not None:
                conn.close()

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_season_ges_authority_api = True
    print("AJPA Mobile: GES por competencia + historial de temporadas habilitados")


def apply_season_ges_authority(runtime, bot) -> None:
    global _RUNTIME, _BOT
    _RUNTIME, _BOT = runtime, bot
    ges.sync_from_ges = _seasonal_sync
    _install_api()
    print("AJPA GES: enlaces y resultados aislados por competencia")
