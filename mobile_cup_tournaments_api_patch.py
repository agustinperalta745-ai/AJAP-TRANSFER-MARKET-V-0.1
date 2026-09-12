"""AJPA Champions League + Europa League tournament API for the mobile app.

Rules implemented:
- Season 1: league positions 1-16 -> Champions; 17-24 -> Europa waiting slots.
- From season 2: top 15 + previous Europa champion -> Champions. If the holder is
  already top 15, position 16 also qualifies so Champions always has 16 clubs.
- The eight Champions first-round losers enter Europa's first round against the
  eight Europa prequalified clubs. After that, both brackets progress normally.
- Staff loads every knockout score (including penalties). Winner/loser propagation
  is automatic and persisted; the public API exposes the complete live bracket.
"""

from __future__ import annotations

import json
import re
import sqlite3
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_read_api
import mobile_write_api

CHAMPIONS = "champions"
EUROPA = "europa"
COMPETITIONS = {CHAMPIONS, EUROPA}
DRAFT = "DRAFT"
ACTIVE = "ACTIVE"
FINISHED = "FINISHED"
ROUNDS = (("R16", 0, 8), ("QF", 1, 4), ("SF", 2, 2), ("F", 3, 1))
ROUND_LABELS = {
    CHAMPIONS: {"R16": "Octavos de final", "QF": "Cuartos de final", "SF": "Semifinales", "F": "Final"},
    EUROPA: {"R16": "Primera ronda", "QF": "Cuartos de final", "SF": "Semifinales", "F": "Final"},
}


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cup_tournament_editions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_number INTEGER NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'DRAFT',
            champions_name TEXT NOT NULL DEFAULT 'Champions League',
            europa_name TEXT NOT NULL DEFAULT 'Europa League',
            champions_champion TEXT,
            europa_champion TEXT,
            created_by INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            finished_at DATETIME
        );
        CREATE TABLE IF NOT EXISTS cup_seed_slots (
            edition_id INTEGER NOT NULL,
            competition TEXT NOT NULL,
            slot_index INTEGER NOT NULL,
            team TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'MANUAL',
            PRIMARY KEY (edition_id, competition, slot_index)
        );
        CREATE TABLE IF NOT EXISTS cup_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            edition_id INTEGER NOT NULL,
            competition TEXT NOT NULL,
            round_key TEXT NOT NULL,
            round_order INTEGER NOT NULL,
            match_index INTEGER NOT NULL,
            home_team TEXT,
            away_team TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            home_penalties INTEGER,
            away_penalties INTEGER,
            winner_team TEXT,
            loser_team TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            source_home TEXT,
            source_away TEXT,
            updated_by INTEGER,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (edition_id, competition, round_key, match_index)
        );
        CREATE INDEX IF NOT EXISTS cup_matches_edition_idx
            ON cup_matches(edition_id, competition, round_order, match_index);
        """
    )


def _staff_session(headers, conn: sqlite3.Connection) -> dict:
    session = mobile_write_api._session(headers, conn)
    if not session.get("is_staff"):
        raise mobile_write_api.ApiFailure("Esta herramienta es exclusiva para Staff.", HTTPStatus.FORBIDDEN)
    return session


def _current_season_number(conn: sqlite3.Connection) -> int:
    if "competition_cycle_state" in mobile_read_api._tables(conn):
        row = conn.execute("SELECT season_number FROM competition_cycle_state WHERE id=1 LIMIT 1").fetchone()
        if row and row["season_number"] is not None:
            return max(1, int(row["season_number"]))
    return 1


def _edition(conn: sqlite3.Connection, edition_id: int):
    return conn.execute("SELECT * FROM cup_tournament_editions WHERE id=? LIMIT 1", (int(edition_id),)).fetchone()


def _latest_edition(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM cup_tournament_editions ORDER BY season_number DESC, id DESC LIMIT 1").fetchone()


def _edition_for_season(conn: sqlite3.Connection, season_number: int):
    return conn.execute("SELECT * FROM cup_tournament_editions WHERE season_number=? LIMIT 1", (int(season_number),)).fetchone()


def _compute_standings_from_matches(conn: sqlite3.Connection, competition_id: int) -> list[dict]:
    if "league_matches" not in mobile_read_api._tables(conn):
        return []
    cols = mobile_read_api._columns(conn, "league_matches")
    if "competition_id" not in cols:
        return []
    rows = conn.execute(
        "SELECT home_team,away_team,home_goals,away_goals FROM league_matches WHERE competition_id=? ORDER BY id",
        (int(competition_id),),
    ).fetchall()
    table: dict[str, dict] = {}
    for row in rows:
        home_name = str(row["home_team"] or "").strip()
        away_name = str(row["away_team"] or "").strip()
        if not home_name or not away_name:
            continue
        for team in (home_name, away_name):
            table.setdefault(team, {"team": team, "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "dg": 0, "pts": 0})
        hg, ag = int(row["home_goals"] or 0), int(row["away_goals"] or 0)
        home, away = table[home_name], table[away_name]
        home["pj"] += 1; away["pj"] += 1
        home["gf"] += hg; home["gc"] += ag; away["gf"] += ag; away["gc"] += hg
        if hg > ag:
            home["pg"] += 1; away["pp"] += 1; home["pts"] += 3
        elif ag > hg:
            away["pg"] += 1; home["pp"] += 1; away["pts"] += 3
        else:
            home["pe"] += 1; away["pe"] += 1; home["pts"] += 1; away["pts"] += 1
    standings = list(table.values())
    for row in standings:
        row["dg"] = int(row["gf"]) - int(row["gc"])
    standings.sort(key=lambda row: (-int(row["pts"]), -int(row["dg"]), -int(row["gf"]), -int(row["pg"]), str(row["team"]).casefold()))
    return standings


def _season_standings(conn: sqlite3.Connection, season_number: int) -> list[dict]:
    if "competition_editions" not in mobile_read_api._tables(conn):
        return []
    row = conn.execute(
        "SELECT * FROM competition_editions WHERE kind='season' AND season_number=? ORDER BY id DESC LIMIT 1",
        (int(season_number),),
    ).fetchone()
    if not row:
        return []
    keys = set(row.keys())
    snapshot = row["final_snapshot_json"] if "final_snapshot_json" in keys else None
    if snapshot:
        try:
            parsed = json.loads(str(snapshot))
            standings = parsed.get("standings") if isinstance(parsed, dict) else None
            if isinstance(standings, list):
                return [item for item in standings if isinstance(item, dict) and str(item.get("team") or "").strip()]
        except Exception:
            pass
    return _compute_standings_from_matches(conn, int(row["id"]))


def _previous_europa_champion(conn: sqlite3.Connection, season_number: int) -> str | None:
    if int(season_number) <= 1:
        return None
    row = conn.execute(
        "SELECT europa_champion FROM cup_tournament_editions WHERE season_number=? LIMIT 1",
        (int(season_number) - 1,),
    ).fetchone()
    value = str(row["europa_champion"] or "").strip() if row else ""
    return value or None


def qualification_suggestion(conn: sqlite3.Connection, season_number: int) -> dict:
    standings = _season_standings(conn, int(season_number))
    ordered = [str(row.get("team") or "").strip() for row in standings]
    ordered = [team for team in ordered if team]
    holder = _previous_europa_champion(conn, int(season_number))
    warnings: list[str] = []

    if int(season_number) == 1:
        champions = ordered[:16]
    else:
        top15 = ordered[:15]
        if holder:
            if any(team.casefold() == holder.casefold() for team in top15):
                champions = ordered[:16]
            else:
                champions = top15 + [holder]
        else:
            champions = ordered[:16]
            warnings.append("No hay campeón de Europa League de la temporada anterior cargado; se usa provisionalmente el Top 16.")

    seen = {team.casefold() for team in champions}
    europa = [team for team in ordered if team.casefold() not in seen][:8]
    if len(champions) < 16:
        warnings.append("La tabla todavía no tiene 16 equipos disponibles para Champions League.")
    if len(europa) < 8:
        warnings.append("La tabla todavía no tiene 8 equipos disponibles para Europa League.")
    return {
        "champions": champions,
        "europa": europa,
        "europa_holder": holder,
        "warnings": warnings,
    }


def _seed_rows(conn: sqlite3.Connection, edition_id: int) -> dict[str, list[dict]]:
    result = {CHAMPIONS: [], EUROPA: []}
    rows = conn.execute(
        "SELECT competition,slot_index,team,source FROM cup_seed_slots WHERE edition_id=? ORDER BY competition,slot_index",
        (int(edition_id),),
    ).fetchall()
    maps = {CHAMPIONS: {}, EUROPA: {}}
    for row in rows:
        comp = str(row["competition"])
        if comp in maps:
            maps[comp][int(row["slot_index"])] = {"team": str(row["team"]), "source": str(row["source"] or "MANUAL")}
    for comp, count in ((CHAMPIONS, 16), (EUROPA, 8)):
        result[comp] = [
            {"slot_index": index, "team": maps[comp].get(index, {}).get("team"), "source": maps[comp].get(index, {}).get("source")}
            for index in range(count)
        ]
    return result


def _match_dict(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "competition": str(row["competition"]),
        "round_key": str(row["round_key"]),
        "round_order": int(row["round_order"]),
        "match_index": int(row["match_index"]),
        "home_team": str(row["home_team"] or "") or None,
        "away_team": str(row["away_team"] or "") or None,
        "home_goals": int(row["home_goals"]) if row["home_goals"] is not None else None,
        "away_goals": int(row["away_goals"]) if row["away_goals"] is not None else None,
        "home_penalties": int(row["home_penalties"]) if row["home_penalties"] is not None else None,
        "away_penalties": int(row["away_penalties"]) if row["away_penalties"] is not None else None,
        "winner_team": str(row["winner_team"] or "") or None,
        "loser_team": str(row["loser_team"] or "") or None,
        "status": str(row["status"]),
        "source_home": str(row["source_home"] or "") or None,
        "source_away": str(row["source_away"] or "") or None,
    }


def _rounds_payload(conn: sqlite3.Connection, edition_id: int) -> dict[str, list[dict]]:
    payload = {CHAMPIONS: [], EUROPA: []}
    for comp in (CHAMPIONS, EUROPA):
        for key, order, _count in ROUNDS:
            rows = conn.execute(
                "SELECT * FROM cup_matches WHERE edition_id=? AND competition=? AND round_key=? ORDER BY match_index",
                (int(edition_id), comp, key),
            ).fetchall()
            payload[comp].append({
                "key": key,
                "label": ROUND_LABELS[comp][key],
                "order": order,
                "matches": [_match_dict(row) for row in rows],
            })
    return payload


def _rules(season_number: int) -> dict:
    return {
        "season_number": int(season_number),
        "champions_name": "Champions League",
        "europa_name": "Europa League",
        "champions_qualification": (
            "Temporada 1: puestos 1.º al 16.º."
            if int(season_number) == 1
            else "Top 15 de liga + campeón vigente de Europa League. Si el campeón ya está en el Top 15, entra también el 16.º."
        ),
        "europa_qualification": "Ocho equipos de liga esperan a los ocho eliminados de la primera ronda de Champions League.",
        "drop_rule": "Solo los 8 perdedores de la primera ronda de Champions League bajan a la primera ronda de Europa League.",
        "next_season_rule": "El campeón de Europa League obtiene plaza en la Champions League de la temporada siguiente sin importar su posición de liga.",
    }


def public_payload(conn: sqlite3.Connection) -> dict:
    current_season = _current_season_number(conn)
    latest = _latest_edition(conn)
    edition_payload = None
    if latest:
        edition_payload = {
            "id": int(latest["id"]),
            "season_number": int(latest["season_number"]),
            "status": str(latest["status"]),
            "champions_name": str(latest["champions_name"]),
            "europa_name": str(latest["europa_name"]),
            "champions_champion": str(latest["champions_champion"] or "") or None,
            "europa_champion": str(latest["europa_champion"] or "") or None,
            "started_at": str(latest["started_at"] or "") or None,
            "finished_at": str(latest["finished_at"] or "") or None,
            "seed_slots": _seed_rows(conn, int(latest["id"])),
            "rounds": _rounds_payload(conn, int(latest["id"])),
        }
    summaries = [
        {
            "id": int(row["id"]),
            "season_number": int(row["season_number"]),
            "status": str(row["status"]),
            "champions_champion": str(row["champions_champion"] or "") or None,
            "europa_champion": str(row["europa_champion"] or "") or None,
        }
        for row in conn.execute("SELECT * FROM cup_tournament_editions ORDER BY season_number DESC, id DESC LIMIT 12").fetchall()
    ]
    clubs = list(mobile_read_api._live_mobile_club_names(conn))
    suggestion = qualification_suggestion(conn, current_season)
    return {
        "rules": _rules(current_season),
        "clubs": clubs,
        "qualification_suggestion": suggestion,
        "edition": edition_payload,
        "editions": summaries,
    }


def create_edition(conn: sqlite3.Connection, session: dict, payload: dict) -> dict:
    season_number = payload.get("season_number")
    season_number = int(season_number) if str(season_number or "").isdigit() else _current_season_number(conn)
    if season_number < 1:
        raise mobile_write_api.ApiFailure("Temporada inválida.")
    existing = _edition_for_season(conn, season_number)
    if existing:
        return {"ok": True, "edition_id": int(existing["id"]), "season_number": season_number, "already_exists": True}
    cur = conn.execute(
        "INSERT INTO cup_tournament_editions(season_number,status,created_by) VALUES(?, 'DRAFT', ?)",
        (season_number, int(session["user_id"])),
    )
    return {"ok": True, "edition_id": int(cur.lastrowid), "season_number": season_number}


def seed_from_table(conn: sqlite3.Connection, session: dict, edition_id: int) -> dict:
    edition = _edition(conn, edition_id)
    if not edition:
        raise mobile_write_api.ApiFailure("La edición no existe.", HTTPStatus.NOT_FOUND)
    if str(edition["status"]) != DRAFT:
        raise mobile_write_api.ApiFailure("Los clasificados solo se pueden cambiar antes de iniciar las copas.", HTTPStatus.CONFLICT)
    suggestion = qualification_suggestion(conn, int(edition["season_number"]))
    conn.execute("DELETE FROM cup_seed_slots WHERE edition_id=?", (int(edition_id),))
    for comp in (CHAMPIONS, EUROPA):
        for index, team in enumerate(suggestion[comp]):
            conn.execute(
                "INSERT INTO cup_seed_slots(edition_id,competition,slot_index,team,source) VALUES(?,?,?,?,?)",
                (int(edition_id), comp, index, team, "TABLA" if comp == EUROPA or int(edition["season_number"]) == 1 else "REGLA_CLASIFICACION"),
            )
    return {"ok": True, "edition_id": int(edition_id), "suggestion": suggestion}


def set_seed_slot(conn: sqlite3.Connection, session: dict, edition_id: int, payload: dict) -> dict:
    edition = _edition(conn, edition_id)
    if not edition:
        raise mobile_write_api.ApiFailure("La edición no existe.", HTTPStatus.NOT_FOUND)
    if str(edition["status"]) != DRAFT:
        raise mobile_write_api.ApiFailure("El cuadro ya empezó; no se pueden cambiar los preclasificados.", HTTPStatus.CONFLICT)
    comp = str(payload.get("competition") or "").strip().lower()
    if comp not in COMPETITIONS:
        raise mobile_write_api.ApiFailure("Competencia inválida.")
    slot_raw = payload.get("slot_index")
    if not str(slot_raw if slot_raw is not None else "").isdigit():
        raise mobile_write_api.ApiFailure("Posición de clasificación inválida.")
    slot = int(slot_raw)
    maximum = 16 if comp == CHAMPIONS else 8
    if slot < 0 or slot >= maximum:
        raise mobile_write_api.ApiFailure("Posición fuera de rango.")
    team = str(payload.get("team") or "").strip()
    conn.execute("DELETE FROM cup_seed_slots WHERE edition_id=? AND competition=? AND slot_index=?", (int(edition_id), comp, slot))
    if team:
        clubs = {name.casefold(): name for name in mobile_read_api._live_mobile_club_names(conn)}
        canonical = clubs.get(team.casefold())
        if not canonical:
            raise mobile_write_api.ApiFailure("Ese equipo no pertenece al catálogo activo de AJPA.")
        duplicate = conn.execute(
            "SELECT competition,slot_index FROM cup_seed_slots WHERE edition_id=? AND team=? COLLATE NOCASE LIMIT 1",
            (int(edition_id), canonical),
        ).fetchone()
        if duplicate:
            raise mobile_write_api.ApiFailure("Ese equipo ya está cargado en otro cupo de clasificación.", HTTPStatus.CONFLICT)
        conn.execute(
            "INSERT INTO cup_seed_slots(edition_id,competition,slot_index,team,source) VALUES(?,?,?,?, 'MANUAL')",
            (int(edition_id), comp, slot, canonical),
        )
    return {"ok": True, "edition_id": int(edition_id), "competition": comp, "slot_index": slot, "team": team or None}


def _insert_match(conn, edition_id: int, comp: str, round_key: str, order: int, index: int, home, away, source_home=None, source_away=None):
    status = "READY" if home and away else "PENDING"
    conn.execute(
        """INSERT INTO cup_matches(
               edition_id,competition,round_key,round_order,match_index,home_team,away_team,status,source_home,source_away
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (int(edition_id), comp, round_key, int(order), int(index), home, away, status, source_home, source_away),
    )


def start_edition(conn: sqlite3.Connection, session: dict, edition_id: int) -> dict:
    edition = _edition(conn, edition_id)
    if not edition:
        raise mobile_write_api.ApiFailure("La edición no existe.", HTTPStatus.NOT_FOUND)
    if str(edition["status"]) != DRAFT:
        raise mobile_write_api.ApiFailure("Las copas ya fueron iniciadas.", HTTPStatus.CONFLICT)
    seeds = _seed_rows(conn, edition_id)
    champions = [row["team"] for row in seeds[CHAMPIONS]]
    europa = [row["team"] for row in seeds[EUROPA]]
    if any(not team for team in champions) or len(champions) != 16:
        raise mobile_write_api.ApiFailure("Completá los 16 clasificados de Champions League antes de iniciar.")
    if any(not team for team in europa) or len(europa) != 8:
        raise mobile_write_api.ApiFailure("Completá los 8 preclasificados de Europa League antes de iniciar.")
    all_seeded = [str(team) for team in champions + europa]
    if len({team.casefold() for team in all_seeded}) != len(all_seeded):
        raise mobile_write_api.ApiFailure("Un equipo está repetido entre Champions y Europa League.", HTTPStatus.CONFLICT)

    conn.execute("DELETE FROM cup_matches WHERE edition_id=?", (int(edition_id),))
    for index in range(8):
        _insert_match(conn, edition_id, CHAMPIONS, "R16", 0, index, champions[index * 2], champions[index * 2 + 1], "Preclasificado Champions", "Preclasificado Champions")
        _insert_match(conn, edition_id, EUROPA, "R16", 0, index, europa[index], None, "Preclasificado Europa", f"Perdedor Champions • Partido {index + 1}")
    for comp in (CHAMPIONS, EUROPA):
        for key, order, count in ROUNDS[1:]:
            for index in range(count):
                _insert_match(conn, edition_id, comp, key, order, index, None, None)
    conn.execute(
        "UPDATE cup_tournament_editions SET status='ACTIVE',started_at=CURRENT_TIMESTAMP,finished_at=NULL,champions_champion=NULL,europa_champion=NULL WHERE id=?",
        (int(edition_id),),
    )
    return {"ok": True, "edition_id": int(edition_id), "status": ACTIVE}


def _next_match(conn, row: sqlite3.Row):
    if str(row["round_key"]) == "F":
        return None
    next_order = int(row["round_order"]) + 1
    next_index = int(row["match_index"]) // 2
    return conn.execute(
        "SELECT * FROM cup_matches WHERE edition_id=? AND competition=? AND round_order=? AND match_index=? LIMIT 1",
        (int(row["edition_id"]), str(row["competition"]), next_order, next_index),
    ).fetchone()


def _europa_drop_match(conn, row: sqlite3.Row):
    if str(row["competition"]) != CHAMPIONS or str(row["round_key"]) != "R16":
        return None
    return conn.execute(
        "SELECT * FROM cup_matches WHERE edition_id=? AND competition='europa' AND round_key='R16' AND match_index=? LIMIT 1",
        (int(row["edition_id"]), int(row["match_index"])),
    ).fetchone()


def _has_result(row) -> bool:
    return bool(row and str(row["status"] or "") == "FINISHED" and row["winner_team"])


def _validate_change_dependencies(conn, row: sqlite3.Row, new_winner: str | None, new_loser: str | None) -> None:
    old_winner = str(row["winner_team"] or "") or None
    old_loser = str(row["loser_team"] or "") or None
    if old_winner and new_winner != old_winner:
        nxt = _next_match(conn, row)
        if _has_result(nxt):
            raise mobile_write_api.ApiFailure("No se puede cambiar el ganador porque su partido de la ronda siguiente ya fue jugado.", HTTPStatus.CONFLICT)
    if old_loser and new_loser != old_loser:
        drop = _europa_drop_match(conn, row)
        if _has_result(drop):
            raise mobile_write_api.ApiFailure("No se puede cambiar el eliminado porque su partido de Europa League ya fue jugado.", HTTPStatus.CONFLICT)


def _set_team_slot(conn, match_id: int, field: str, team: str | None) -> None:
    if field not in {"home_team", "away_team"}:
        raise ValueError("invalid slot")
    conn.execute(f"UPDATE cup_matches SET {field}=?,status=CASE WHEN ? IS NOT NULL AND COALESCE({('away_team' if field == 'home_team' else 'home_team')},'')<>'' THEN 'READY' ELSE 'PENDING' END,updated_at=CURRENT_TIMESTAMP WHERE id=?", (team, team, int(match_id)))


def _propagate(conn, row: sqlite3.Row, winner: str, loser: str) -> None:
    nxt = _next_match(conn, row)
    if nxt:
        field = "home_team" if int(row["match_index"]) % 2 == 0 else "away_team"
        _set_team_slot(conn, int(nxt["id"]), field, winner)
    drop = _europa_drop_match(conn, row)
    if drop:
        _set_team_slot(conn, int(drop["id"]), "away_team", loser)


def _unpropagate(conn, row: sqlite3.Row) -> None:
    old_winner = str(row["winner_team"] or "") or None
    old_loser = str(row["loser_team"] or "") or None
    nxt = _next_match(conn, row)
    if nxt and old_winner:
        field = "home_team" if int(row["match_index"]) % 2 == 0 else "away_team"
        if str(nxt[field] or "").casefold() == old_winner.casefold():
            _set_team_slot(conn, int(nxt["id"]), field, None)
    drop = _europa_drop_match(conn, row)
    if drop and old_loser and str(drop["away_team"] or "").casefold() == old_loser.casefold():
        _set_team_slot(conn, int(drop["id"]), "away_team", None)


def _int_score(value, label: str) -> int:
    if isinstance(value, bool) or not str(value if value is not None else "").isdigit():
        raise mobile_write_api.ApiFailure(f"{label} debe ser un número entero igual o mayor a 0.")
    result = int(value)
    if result < 0 or result > 99:
        raise mobile_write_api.ApiFailure(f"{label} está fuera de rango.")
    return result


def save_result(conn: sqlite3.Connection, session: dict, match_id: int, payload: dict) -> dict:
    row = conn.execute("SELECT * FROM cup_matches WHERE id=? LIMIT 1", (int(match_id),)).fetchone()
    if not row:
        raise mobile_write_api.ApiFailure("El partido no existe.", HTTPStatus.NOT_FOUND)
    edition = _edition(conn, int(row["edition_id"]))
    if not edition or str(edition["status"]) not in {ACTIVE, FINISHED}:
        raise mobile_write_api.ApiFailure("La copa todavía no está activa.", HTTPStatus.CONFLICT)
    if not row["home_team"] or not row["away_team"]:
        raise mobile_write_api.ApiFailure("Este cruce todavía está esperando un rival.", HTTPStatus.CONFLICT)

    if bool(payload.get("clear")):
        if not _has_result(row):
            return {"ok": True, "match_id": int(match_id), "cleared": True}
        _validate_change_dependencies(conn, row, None, None)
        _unpropagate(conn, row)
        conn.execute(
            """UPDATE cup_matches SET home_goals=NULL,away_goals=NULL,home_penalties=NULL,away_penalties=NULL,
               winner_team=NULL,loser_team=NULL,status='READY',updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (int(session["user_id"]), int(match_id)),
        )
        if str(row["round_key"]) == "F":
            field = "champions_champion" if str(row["competition"]) == CHAMPIONS else "europa_champion"
            conn.execute(f"UPDATE cup_tournament_editions SET {field}=NULL,status='ACTIVE',finished_at=NULL WHERE id=?", (int(row["edition_id"]),))
        return {"ok": True, "match_id": int(match_id), "cleared": True}

    hg = _int_score(payload.get("home_goals"), "Goles del local")
    ag = _int_score(payload.get("away_goals"), "Goles del visitante")
    hp_raw, ap_raw = payload.get("home_penalties"), payload.get("away_penalties")
    penalties_supplied = hp_raw not in (None, "") or ap_raw not in (None, "")
    hp = ap = None
    if hg == ag:
        if not penalties_supplied:
            raise mobile_write_api.ApiFailure("En un empate eliminatorio tenés que cargar el resultado de los penales.")
        hp = _int_score(hp_raw, "Penales del local")
        ap = _int_score(ap_raw, "Penales del visitante")
        if hp == ap:
            raise mobile_write_api.ApiFailure("La tanda de penales no puede terminar empatada.")
        home_wins = hp > ap
    else:
        if penalties_supplied:
            raise mobile_write_api.ApiFailure("Solo cargá penales cuando el partido termina empatado.")
        home_wins = hg > ag

    home = str(row["home_team"])
    away = str(row["away_team"])
    winner, loser = (home, away) if home_wins else (away, home)
    _validate_change_dependencies(conn, row, winner, loser)
    if _has_result(row):
        _unpropagate(conn, row)

    conn.execute(
        """UPDATE cup_matches SET home_goals=?,away_goals=?,home_penalties=?,away_penalties=?,
           winner_team=?,loser_team=?,status='FINISHED',updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (hg, ag, hp, ap, winner, loser, int(session["user_id"]), int(match_id)),
    )
    refreshed = conn.execute("SELECT * FROM cup_matches WHERE id=?", (int(match_id),)).fetchone()
    _propagate(conn, refreshed, winner, loser)

    if str(row["round_key"]) == "F":
        field = "champions_champion" if str(row["competition"]) == CHAMPIONS else "europa_champion"
        conn.execute(f"UPDATE cup_tournament_editions SET {field}=? WHERE id=?", (winner, int(row["edition_id"])))
        updated_edition = _edition(conn, int(row["edition_id"]))
        if updated_edition and updated_edition["champions_champion"] and updated_edition["europa_champion"]:
            conn.execute("UPDATE cup_tournament_editions SET status='FINISHED',finished_at=CURRENT_TIMESTAMP WHERE id=?", (int(row["edition_id"]),))

    return {"ok": True, "match_id": int(match_id), "winner": winner, "loser": loser}


def _bootstrap_schema() -> None:
    try:
        with mobile_write_api.write_db() as conn:
            ensure_schema(conn)
            conn.commit()
    except Exception as exc:
        print(f"AJPA cups schema bootstrap warning: {type(exc).__name__}: {exc}")


def apply_mobile_cup_tournaments_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_cup_tournaments_api_patch", False):
        return
    _bootstrap_schema()
    original_get, original_post = handler.do_GET, handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/cups":
            return original_get(self)
        try:
            with mobile_read_api.readonly_db() as conn:
                self._json(public_payload(conn))
        except Exception as exc:
            print(f"AJPA cups GET error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudieron cargar las copas."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        edition_match = re.fullmatch(r"/api/v1/cups/(\d+)/(seed-from-table|slots|start)", path)
        result_match = re.fullmatch(r"/api/v1/cups/matches/(\d+)/result", path)
        if path != "/api/v1/cups/edition" and not edition_match and not result_match:
            return original_post(self)
        conn = None
        try:
            payload = mobile_write_api._read_json(self)
            with mobile_write_api.write_db() as conn:
                ensure_schema(conn)
                session = _staff_session(self.headers, conn)
                if path == "/api/v1/cups/edition":
                    result = create_edition(conn, session, payload)
                elif result_match:
                    result = save_result(conn, session, int(result_match.group(1)), payload)
                else:
                    edition_id = int(edition_match.group(1))
                    action = edition_match.group(2)
                    if action == "seed-from-table":
                        result = seed_from_table(conn, session, edition_id)
                    elif action == "slots":
                        result = set_seed_slot(conn, session, edition_id, payload)
                    else:
                        result = start_edition(conn, session, edition_id)
                conn.commit()
                self._json(result)
        except mobile_write_api.ApiFailure as exc:
            if conn is not None:
                try: conn.rollback()
                except Exception: pass
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            if conn is not None:
                try: conn.rollback()
                except Exception: pass
            print(f"AJPA cups POST error: {type(exc).__name__}: {exc}")
            self._json({"error": "internal_error", "message": "No se pudo actualizar la copa."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_mobile_cup_tournaments_api_patch = True
    print("AJPA Mobile: Champions League + Europa League bracket API enabled")
