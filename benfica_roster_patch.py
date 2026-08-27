"""Load Benfica from data/Benfica.json with full PES6 stats and AJAP OVR."""

from __future__ import annotations

import json
from pathlib import Path

import fiorentina_roster_patch as roster_base
import team_assignment as teams

BENFICA = "Benfica"
COUNTRY = "Portugal"
MIGRATION_MARKER = "benfica_json_v1_ovr3_20260827"
SOURCE = "Benfica.json • OVR AJPA promedio de 3 stats • 2026-08-27"
SOURCE_PATH = Path(__file__).resolve().parent / "data" / "Benfica.json"

POSITION_BY_PLAYER = {'Simao': 'WF/LMF',
 'Miccoli': 'SS/CF',
 'Nuno Gomes': 'CF',
 'Kikin': 'CF',
 'Mantorras': 'CF',
 'Marcel': 'CF',
 'Petit': 'DMF/CMF',
 'Katsouranis': 'DMF/CMF',
 'Rui Costa': 'AMF/CMF',
 'Beto': 'DMF/CMF',
 'Marco Ferreira': 'RMF/WF',
 'Paulo Jorge': 'LMF/WF',
 'Manu': 'RMF/WF',
 'Nuno Assis': 'AMF/CMF',
 'Diego': 'AMF/CMF',
 'Joao Coimbra': 'CMF/DMF',
 'Luisao': 'CB',
 'Anderson Cleber': 'CB',
 'Nelson': 'RB/RMF',
 'Leo': 'LB/LMF',
 'Alcides Eduardo': 'CB/RB',
 'Ricardo Rocha': 'CB/RB',
 'Tiago Gomes': 'LB',
 'Miguelito': 'LB',
 'Moretto': 'GK',
 'Quim': 'GK',
 'Moreira': 'GK'}

STAT_MAP = roster_base.STAT_MAP
ATTR_COLUMNS = roster_base.ATTR_COLUMNS


def _load_source():
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if str(payload.get("equipo", "")).strip().casefold() != BENFICA.casefold():
        raise ValueError("Benfica.json no corresponde a Benfica")
    players = payload.get("jugadores") or []
    by_name = {str(player["nombre"]).strip(): player for player in players}
    if len(players) != 27 or set(by_name) != set(POSITION_BY_PLAYER):
        missing = sorted(set(POSITION_BY_PLAYER) - set(by_name))
        extra = sorted(set(by_name) - set(POSITION_BY_PLAYER))
        raise ValueError(
            f"Benfica.json inválido: jugadores={len(players)} faltan={missing or '-'} sobran={extra or '-'}"
        )
    return by_name


BENFICA_DATA = _load_source()


def _rating(position, stats):
    return roster_base._rating(position, stats)


BENFICA_ROSTER = [
    (name, POSITION_BY_PLAYER[name], _rating(POSITION_BY_PLAYER[name], BENFICA_DATA[name]["stats"]))
    for name in POSITION_BY_PLAYER
]

if not any(name.casefold() == BENFICA.casefold() for name, _country in teams.OFFICIAL_TEAMS):
    teams.OFFICIAL_TEAMS.append((BENFICA, COUNTRY))
teams.OFFICIAL[BENFICA.casefold()] = BENFICA


def _upsert_attributes(conn, player_id, payload):
    raw = payload.get("stats") or {}
    values = {target: raw.get(source) for source, target in STAT_MAP.items()}
    insert_columns = ["player_id", *ATTR_COLUMNS, "source", "updated_at"]
    placeholders = ["?" for _ in insert_columns[:-1]] + ["CURRENT_TIMESTAMP"]
    params = [player_id, *[values.get(column) for column in ATTR_COLUMNS], SOURCE]
    updates = [f"{column} = excluded.{column}" for column in ATTR_COLUMNS]
    updates += ["source = excluded.source", "updated_at = CURRENT_TIMESTAMP"]
    conn.execute(
        f"INSERT INTO pes6_player_attributes ({', '.join(insert_columns)}) "
        f"VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT(player_id) DO UPDATE SET {', '.join(updates)}",
        params,
    )
    conn.execute("DELETE FROM pes6_player_special_abilities WHERE player_id = ?", (player_id,))
    for ability in payload.get("habilidades_especiales") or []:
        conn.execute(
            "INSERT OR IGNORE INTO pes6_player_special_abilities "
            "(player_id, ability, source) VALUES (?, ?, ?)",
            (player_id, str(ability).strip(), SOURCE),
        )


def _sync_connection(runtime, conn):
    from lyon_test_seed import minimum_for_rating

    roster_base._ensure_schema(runtime, conn)
    names = [name for name, _position, _rating_value in BENFICA_ROSTER]
    marks = ",".join("?" for _ in names)
    present = conn.execute(
        f"SELECT COUNT(*) AS n FROM roster_players WHERE name COLLATE NOCASE IN ({marks})",
        tuple(names),
    ).fetchone()
    if int(present["n"] if present else 0) < len(BENFICA_ROSTER):
        conn.execute("DELETE FROM seed_state WHERE key = ?", (MIGRATION_MARKER,))

    done = conn.execute("SELECT 1 FROM seed_state WHERE key = ?", (MIGRATION_MARKER,)).fetchone()
    if done:
        conn.execute(
            "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
            "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
            (BENFICA, COUNTRY),
        )
        return 0

    changed = 0
    for name, position, rating in BENFICA_ROSTER:
        row = conn.execute(
            "SELECT id, club FROM roster_players WHERE name = ? COLLATE NOCASE LIMIT 1",
            (name,),
        ).fetchone()
        if row:
            player_id = int(row["id"])
            conn.execute(
                "UPDATE roster_players SET position = ?, rating = ?, min_sale_value = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (position, rating, minimum_for_rating(rating), player_id),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO roster_players "
                "(name, position, club, added_by, rating, min_sale_value, updated_at) "
                "VALUES (?, ?, ?, NULL, ?, ?, CURRENT_TIMESTAMP)",
                (name, position, BENFICA, rating, minimum_for_rating(rating)),
            )
            player_id = int(cursor.lastrowid)
        _upsert_attributes(conn, player_id, BENFICA_DATA[name])
        changed += 1

    conn.execute(
        "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
        "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
        (BENFICA, COUNTRY),
    )
    if "deleted_teams" in roster_base._tables(conn):
        conn.execute("DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE", (BENFICA,))
    conn.execute("INSERT OR IGNORE INTO seed_state (key) VALUES (?)", (MIGRATION_MARKER,))
    return changed


def apply_benfica_json(runtime):
    if getattr(runtime, "_ajap_benfica_json", False):
        return
    base_db = runtime.db
    synced_guilds = set()

    def benfica_synced_db():
        conn = base_db()
        guild_id = int(runtime.current_guild_id())
        if guild_id in synced_guilds:
            return conn
        try:
            changed = _sync_connection(runtime, conn)
            conn.commit()
            synced_guilds.add(guild_id)
            if changed:
                print(
                    f"AJAP Benfica cargado: guild={guild_id} • "
                    f"{len(BENFICA_ROSTER)} jugadores desde Benfica.json"
                )
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = benfica_synced_db
    runtime._ajap_benfica_json = True
    print(
        f"AJAP migración Benfica activa: {len(BENFICA_ROSTER)} jugadores • "
        "OVR AJPA de 3 stats"
    )


OVR_BY_PLAYER = {name: rating for name, _position, rating in BENFICA_ROSTER}
print(f"AJAP Benfica JSON listo: {len(BENFICA_ROSTER)} jugadores")
