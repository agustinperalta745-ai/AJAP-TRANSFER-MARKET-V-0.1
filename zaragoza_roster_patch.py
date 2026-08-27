"""Load Real Zaragoza from data/Zaragoza.json with full PES6 stats and AJPA OVR."""

from __future__ import annotations

import json
from pathlib import Path

import fiorentina_roster_patch as roster_base
import team_assignment as teams

ZARAGOZA = "Real Zaragoza"
COUNTRY = "España"
MIGRATION_MARKER = "real_zaragoza_json_v1_ovr3_20260827"
SOURCE = "Zaragoza.json • OVR AJPA promedio de 3 stats • 2026-08-27"
SOURCE_PATH = Path(__file__).resolve().parent / "data" / "Zaragoza.json"

POSITION_BY_PLAYER = {
    "Ewerthon": "CF",
    "D. Milito": "CF",
    "Sergio Garcia": "SS/CF",
    "Ponzio": "DMF/RB",
    "Zapater": "DMF/CMF",
    "Celades": "CMF/DMF",
    "Oscar": "AMF/SS",
    "D Alessandro": "AMF/WF",
    "Movilla": "CMF/DMF",
    "Diogo": "RB",
    "Aimar": "AMF/SS",
    "Lafita": "RMF/WF",
    "Sergio": "CB",
    "G. Milito": "CB",
    "Juanfran": "LB/LMF",
    "Cesar Jimenez": "CB",
    "Pique": "CB",
    "Chus Herrero": "CB",
    "Cuartero": "CB/RB",
    "Aranzabal": "LB",
    "Cesar Sanchez": "GK",
    "Miguel": "GK",
}

STAT_MAP = roster_base.STAT_MAP
ATTR_COLUMNS = roster_base.ATTR_COLUMNS


def _normalize_stats(stats):
    """Accept the two abbreviated goalkeeper keys present in the supplied JSON."""
    normalized = dict(stats or {})
    if "ataque" not in normalized and "ataq" in normalized:
        normalized["ataque"] = normalized["ataq"]
    if "defensa" not in normalized and "def" in normalized:
        normalized["defensa"] = normalized["def"]
    return normalized


def _load_source():
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if str(payload.get("equipo", "")).strip().casefold() != ZARAGOZA.casefold():
        raise ValueError("Zaragoza.json no corresponde a Real Zaragoza")
    players = payload.get("jugadores") or []
    by_name = {}
    for player in players:
        name = str(player["nombre"]).strip()
        item = dict(player)
        item["stats"] = _normalize_stats(item.get("stats"))
        by_name[name] = item
    if len(players) != 22 or set(by_name) != set(POSITION_BY_PLAYER):
        missing = sorted(set(POSITION_BY_PLAYER) - set(by_name))
        extra = sorted(set(by_name) - set(POSITION_BY_PLAYER))
        raise ValueError(
            f"Zaragoza.json inválido: jugadores={len(players)} faltan={missing or '-'} sobran={extra or '-'}"
        )
    return by_name


ZARAGOZA_DATA = _load_source()


def _rating(position, stats):
    return roster_base._rating(position, stats)


ZARAGOZA_ROSTER = [
    (name, POSITION_BY_PLAYER[name], _rating(POSITION_BY_PLAYER[name], ZARAGOZA_DATA[name]["stats"]))
    for name in POSITION_BY_PLAYER
]

if not any(name.casefold() == ZARAGOZA.casefold() for name, _country in teams.OFFICIAL_TEAMS):
    teams.OFFICIAL_TEAMS.append((ZARAGOZA, COUNTRY))
teams.OFFICIAL[ZARAGOZA.casefold()] = ZARAGOZA


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
    names = [name for name, _position, _rating_value in ZARAGOZA_ROSTER]
    marks = ",".join("?" for _ in names)
    present = conn.execute(
        f"SELECT COUNT(*) AS n FROM roster_players WHERE name COLLATE NOCASE IN ({marks})",
        tuple(names),
    ).fetchone()
    if int(present["n"] if present else 0) < len(ZARAGOZA_ROSTER):
        conn.execute("DELETE FROM seed_state WHERE key = ?", (MIGRATION_MARKER,))

    done = conn.execute("SELECT 1 FROM seed_state WHERE key = ?", (MIGRATION_MARKER,)).fetchone()
    if done:
        conn.execute(
            "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
            "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
            (ZARAGOZA, COUNTRY),
        )
        return 0

    changed = 0
    for name, position, rating in ZARAGOZA_ROSTER:
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
                (name, position, ZARAGOZA, rating, minimum_for_rating(rating)),
            )
            player_id = int(cursor.lastrowid)
        _upsert_attributes(conn, player_id, ZARAGOZA_DATA[name])
        changed += 1

    conn.execute(
        "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
        "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
        (ZARAGOZA, COUNTRY),
    )
    if "deleted_teams" in roster_base._tables(conn):
        conn.execute("DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE", (ZARAGOZA,))
    conn.execute("INSERT OR IGNORE INTO seed_state (key) VALUES (?)", (MIGRATION_MARKER,))
    return changed


def apply_zaragoza_json(runtime):
    if getattr(runtime, "_ajap_zaragoza_json", False):
        return
    base_db = runtime.db
    synced_guilds = set()

    def zaragoza_synced_db():
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
                    f"AJAP Real Zaragoza cargado: guild={guild_id} • "
                    f"{len(ZARAGOZA_ROSTER)} jugadores desde Zaragoza.json"
                )
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = zaragoza_synced_db
    runtime._ajap_zaragoza_json = True
    print(
        f"AJAP migración Real Zaragoza activa: {len(ZARAGOZA_ROSTER)} jugadores • "
        "OVR AJPA de 3 stats"
    )


OVR_BY_PLAYER = {name: rating for name, _position, rating in ZARAGOZA_ROSTER}
print(f"AJAP Real Zaragoza JSON listo: {len(ZARAGOZA_ROSTER)} jugadores")
