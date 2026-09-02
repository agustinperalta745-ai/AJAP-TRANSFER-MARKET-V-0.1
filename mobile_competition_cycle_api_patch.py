"""Mobile Staff API for the official AJPA competition lifecycle."""

from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlparse

import competition_cycle as cycle
import mobile_parity_api_patch as parity
import mobile_read_api
import mobile_write_api


def _staff(headers, conn):
    session = mobile_write_api._session(headers, conn)
    if not session.get("is_staff"):
        raise mobile_write_api.ApiFailure(
            "Esta herramienta es exclusiva para Staff.", HTTPStatus.FORBIDDEN
        )
    return session


def _filtered_league_payload(conn, base_payload):
    """Replace only active standings/scorers; keep all-time history/cards intact."""
    cycle.ensure_schema(conn)
    cid = cycle.active_competition_id(conn)
    teams = list(mobile_read_api._live_mobile_club_names(conn))
    table = {
        team: {"team":team,"pj":0,"pg":0,"pe":0,"pp":0,"gf":0,"gc":0,"dg":0,"pts":0}
        for team in teams
    }
    if cid is not None and "league_matches" in parity._tables(conn):
        rows = conn.execute(
            "SELECT home_team,away_team,home_goals,away_goals FROM league_matches WHERE competition_id=? ORDER BY id",
            (int(cid),),
        ).fetchall()
        for row in rows:
            hn, an = str(row["home_team"] or "").strip(), str(row["away_team"] or "").strip()
            for name in (hn, an):
                if name and name not in table:
                    table[name] = {"team":name,"pj":0,"pg":0,"pe":0,"pp":0,"gf":0,"gc":0,"dg":0,"pts":0}
            h, a = table.get(hn), table.get(an)
            if not h or not a:
                continue
            hg, ag = int(row["home_goals"]), int(row["away_goals"])
            h["pj"] += 1; a["pj"] += 1
            h["gf"] += hg; h["gc"] += ag; a["gf"] += ag; a["gc"] += hg
            if hg > ag:
                h["pg"] += 1; a["pp"] += 1; h["pts"] += 3
            elif ag > hg:
                a["pg"] += 1; h["pp"] += 1; a["pts"] += 3
            else:
                h["pe"] += 1; a["pe"] += 1; h["pts"] += 1; a["pts"] += 1
    standings = list(table.values())
    for row in standings:
        row["dg"] = int(row["gf"]) - int(row["gc"])
    standings.sort(key=lambda r:(-r["pts"],-r["dg"],-r["gf"],-r["pg"],str(r["team"]).casefold()))

    scorers = []
    if cid is not None and "league_goal_events" in parity._tables(conn):
        rows = conn.execute(
            """SELECT player,team,SUM(goals) goals FROM league_goal_events
               WHERE competition_id=?
               GROUP BY player COLLATE NOCASE,COALESCE(team,'') COLLATE NOCASE
               ORDER BY goals DESC,player COLLATE NOCASE LIMIT 50""",
            (int(cid),),
        ).fetchall()
        scorers = [
            {"player":str(r["player"]),"team":str(r["team"] or ""),"goals":int(r["goals"] or 0)}
            for r in rows
        ]

    payload = dict(base_payload)
    payload["standings"] = standings
    payload["scorers"] = scorers
    payload["cycle"] = cycle.state_payload(conn)
    return payload


def apply_mobile_competition_cycle_api_patch():
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_competition_cycle", False):
        return

    # History patch has already wrapped parity.league_payload at this point.
    current_league_payload = parity.league_payload
    if not getattr(current_league_payload, "_ajpa_cycle_filtered", False):
        def league_payload(conn):
            base = current_league_payload(conn)
            return _filtered_league_payload(conn, base)
        league_payload._ajpa_cycle_filtered = True
        parity.league_payload = league_payload

    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/admin/competition-cycle":
            return original_get(self)
        conn = None
        try:
            with mobile_write_api.write_db() as conn:
                mobile_write_api.ensure_schema(conn)
                _staff(self.headers, conn)
                payload = cycle.state_payload(conn)
                conn.commit()
                self._json(payload)
                return
        except mobile_write_api.ApiFailure as exc:
            if conn is not None:
                try: conn.rollback()
                except Exception: pass
            self._json({"error":"request","message":exc.message}, exc.status)
        except Exception as exc:
            if conn is not None:
                try: conn.rollback()
                except Exception: pass
            print(f"AJPA cycle mobile GET error: {type(exc).__name__}: {exc}")
            self._json({"error":"internal_error","message":"No se pudo cargar la etapa AJPA."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/admin/competition-cycle/advance":
            return original_post(self)
        conn = None
        try:
            body = mobile_write_api._read_json(self)
            conn = mobile_write_api.write_db()
            mobile_write_api.ensure_schema(conn)
            session = _staff(self.headers, conn)
            expected = str(body.get("expected_phase") or "").strip() or None
            result = cycle.advance(conn, int(session["user_id"]), expected)
            self._json({"ok":True,"cycle":result})
            return
        except cycle.CycleError as exc:
            if conn is not None:
                try: conn.rollback()
                except Exception: pass
            self._json({"error":"cycle","message":str(exc)}, HTTPStatus.CONFLICT)
        except mobile_write_api.ApiFailure as exc:
            if conn is not None:
                try: conn.rollback()
                except Exception: pass
            self._json({"error":"request","message":exc.message}, exc.status)
        except Exception as exc:
            if conn is not None:
                try: conn.rollback()
                except Exception: pass
            print(f"AJPA cycle mobile POST error: {type(exc).__name__}: {exc}")
            self._json({"error":"internal_error","message":"No se pudo cambiar la etapa AJPA."}, HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            if conn is not None:
                conn.close()

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_competition_cycle = True
    print("AJPA Mobile: control Staff del ciclo oficial habilitado")
