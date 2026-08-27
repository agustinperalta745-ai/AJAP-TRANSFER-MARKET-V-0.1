"""Load Celta de Vigo from data/Celta de Vigo.json with full PES6 stats and AJPA OVR."""

from __future__ import annotations

import json
from pathlib import Path

import fiorentina_roster_patch as roster_base
import team_assignment as teams

CELTA = "Celta de Vigo"
COUNTRY = "España"
MIGRATION_MARKER = "celta_de_vigo_json_v1_ovr3_20260827"
SOURCE = "Celta de Vigo.json • OVR AJPA promedio de 3 stats • 2026-08-27"
SOURCE_PATH = Path(__file__).resolve().parent / "data" / "Celta de Vigo.json"

POSITION_BY_PLAYER = {
    "Baiano": "CF",
    "Jesus Perera": "CF",
    "De Ridder": "WF/RMF",
    "Guayre": "WF/CF",
    "Javi Guerrero": "CF",
    "Iriney": "DMF/CMF",
    "Borja Oubiña": "DMF/CMF",
    "Gustavo Lopez": "LMF/WF",
    "Nene": "WF/LMF",
    "Canobbio": "AMF/SS",
    "P.Garcia": "DMF/CMF",
    "Antonio Nuñez": "RMF/WF",
    "Jorge": "AMF/CMF",
    "Jonathan": "RMF/WF",
    "Lequi": "CB",
    "P. Contreras": "CB",
    "George Lucas": "RB",
    "Angel": "RB",
    "Yago": "CB",
    "Placente": "LB",
    "Pinto": "GK",
    "Esteban": "GK",
    "Marcos Bermudez": "CB",
}

STAT_MAP = roster_base.STAT_MAP
ATTR_COLUMNS = roster_base.ATTR_COLUMNS


def _load_source():
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if str(payload.get("equipo", "")).strip().casefold() != CELTA.casefold():
        raise ValueError("Celta de Vigo.json no corresponde a Celta de Vigo")
    players = payload.get("jugadores") or []
    by_name = {str(player["nombre"]).strip(): player for player in players}
    if len(players) != 23 or set(by_name) != set(POSITION_BY_PLAYER):
        missing = sorted(set(POSITION_BY_PLAYER) - set(by_name))
        extra = sorted(set(by_name) - set(POSITION_BY_PLAYER))
        raise ValueError(
            f"Celta de Vigo.json inválido: jugadores={len(players)} faltan={missing or '-'} sobran={extra or '-'}"
        )
    return by_name


CELTA_DATA = _load_source()


def _rating(position, stats):
    return roster_base._rating(position, stats)


CELTA_ROSTER = [
    (name, POSITION_BY_PLAYER[name], _rating(POSITION_BY_PLAYER[name], CELTA_DATA[name]["stats"]))
    for name in POSITION_BY_PLAYER
]

if not any(name.casefold() == CELTA.casefold() for name, _country in teams.OFFICIAL_TEAMS):
    teams.OFFICIAL_TEAMS.append((CELTA, COUNTRY))
teams.OFFICIAL[CELTA.casefold()] = CELTA


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
    names = [name for name, _position, _rating_value in CELTA_ROSTER]
    marks = ",".join("?" for _ in names)
    present = conn.execute(
        f"SELECT COUNT(*) AS n FROM roster_players WHERE name COLLATE NOCASE IN ({marks})",
        tuple(names),
    ).fetchone()
    if int(present["n"] if present else 0) < len(CELTA_ROSTER):
        conn.execute("DELETE FROM seed_state WHERE key = ?", (MIGRATION_MARKER,))

    done = conn.execute("SELECT 1 FROM seed_state WHERE key = ?", (MIGRATION_MARKER,)).fetchone()
    if done:
        conn.execute(
            "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
            "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
            (CELTA, COUNTRY),
        )
        return 0

    changed = 0
    for name, position, rating in CELTA_ROSTER:
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
                (name, position, CELTA, rating, minimum_for_rating(rating)),
            )
            player_id = int(cursor.lastrowid)
        _upsert_attributes(conn, player_id, CELTA_DATA[name])
        changed += 1

    conn.execute(
        "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
        "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
        (CELTA, COUNTRY),
    )
    if "deleted_teams" in roster_base._tables(conn):
        conn.execute("DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE", (CELTA,))
    conn.execute("INSERT OR IGNORE INTO seed_state (key) VALUES (?)", (MIGRATION_MARKER,))
    return changed


def apply_celta_json(runtime):
    if getattr(runtime, "_ajap_celta_json", False):
        return
    base_db = runtime.db
    synced_guilds = set()

    def celta_synced_db():
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
                    f"AJAP Celta de Vigo cargado: guild={guild_id} • "
                    f"{len(CELTA_ROSTER)} jugadores desde Celta de Vigo.json"
                )
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = celta_synced_db
    runtime._ajap_celta_json = True
    print(
        f"AJAP migración Celta de Vigo activa: {len(CELTA_ROSTER)} jugadores • "
        "OVR AJPA de 3 stats"
    )


OVR_BY_PLAYER = {name: rating for name, _position, rating in CELTA_ROSTER}
print(f"AJAP Celta de Vigo JSON listo: {len(CELTA_ROSTER)} jugadores")
