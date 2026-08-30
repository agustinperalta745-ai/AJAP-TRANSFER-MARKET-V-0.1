"""Load Feyenoord from data/Feyenoord.json with full PES6 stats and AJAP OVR."""

from __future__ import annotations

import json
from pathlib import Path

import fiorentina_roster_patch as roster_base
import guild_isolation_patch as guild_isolation
import team_assignment as teams

FEYENOORD = "Feyenoord"
COUNTRY = "Países Bajos"
MIGRATION_MARKER = "feyenoord_json_v1_ovr3_20260830"
SOURCE = "Feyenoord.json • OVR AJPA promedio de 3 stats • 2026-08-30"
SOURCE_PATH = Path(__file__).resolve().parent / "data" / "Feyenoord.json"

POSITION_BY_PLAYER = {
    "Castelen": "WF/RMF",
    "Huysegems": "CF/WF",
    "Charisteas": "CF",
    "Kolkka": "WF/LMF",
    "De Ceulaer": "CF/SS",
    "Vincken": "WF/RMF",
    "Boussaboun": "WF/SS",
    "Van Hooijdonk": "CF",
    "De Guzman": "CMF/AMF",
    "Lucius": "DMF/RB",
    "Hofs": "AMF/CMF",
    "Schreuder": "DMF/CMF",
    "Buijs": "CMF/DMF",
    "Pardo": "AMF/SMF",
    "Abubakari": "DMF/CMF",
    "Sammuel": "AMF/CMF",
    "Vlaar": "CB",
    "Bahia": "CB",
    "Greene": "RB/CB",
    "Drenthe": "LMF/LB",
    "Derijck": "CB/DMF",
    "Collen": "RB/CB",
    "Timmer": "GK",
    "Lodewijks": "GK",
    "Ekramy": "GK",
}

STAT_MAP = roster_base.STAT_MAP
ATTR_COLUMNS = roster_base.ATTR_COLUMNS


def _load_source():
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if str(payload.get("equipo", "")).strip().casefold() != FEYENOORD.casefold():
        raise ValueError("Feyenoord.json no corresponde a Feyenoord")
    players = payload.get("jugadores") or []
    by_name = {str(player["nombre"]).strip(): player for player in players}
    if len(players) != len(POSITION_BY_PLAYER) or set(by_name) != set(POSITION_BY_PLAYER):
        missing = sorted(set(POSITION_BY_PLAYER) - set(by_name))
        extra = sorted(set(by_name) - set(POSITION_BY_PLAYER))
        raise ValueError(
            f"Feyenoord.json inválido: jugadores={len(players)} "
            f"faltan={missing or '-'} sobran={extra or '-'}"
        )
    return by_name


FEYENOORD_DATA = _load_source()


def _rating(position, stats):
    return roster_base._rating(position, stats)


FEYENOORD_ROSTER = [
    (name, POSITION_BY_PLAYER[name], _rating(POSITION_BY_PLAYER[name], FEYENOORD_DATA[name]["stats"]))
    for name in POSITION_BY_PLAYER
]

if not any(name.casefold() == FEYENOORD.casefold() for name, _country in teams.OFFICIAL_TEAMS):
    teams.OFFICIAL_TEAMS.append((FEYENOORD, COUNTRY))
teams.OFFICIAL[FEYENOORD.casefold()] = FEYENOORD


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

    names = [name for name, _position, _rating_value in FEYENOORD_ROSTER]
    marks = ",".join("?" for _ in names)
    present = conn.execute(
        f"SELECT COUNT(*) AS n FROM roster_players WHERE name COLLATE NOCASE IN ({marks})",
        tuple(names),
    ).fetchone()
    if int(present["n"] if present else 0) < len(FEYENOORD_ROSTER):
        conn.execute("DELETE FROM seed_state WHERE key = ?", (MIGRATION_MARKER,))

    done = conn.execute("SELECT 1 FROM seed_state WHERE key = ?", (MIGRATION_MARKER,)).fetchone()
    if done:
        conn.execute(
            "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
            "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
            (FEYENOORD, COUNTRY),
        )
        return 0

    changed = 0
    for name, position, rating in FEYENOORD_ROSTER:
        row = conn.execute(
            "SELECT id, club FROM roster_players WHERE name = ? COLLATE NOCASE LIMIT 1",
            (name,),
        ).fetchone()
        if row:
            player_id = int(row["id"])
            # Preserve the current club if this player was already transferred.
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
                (name, position, FEYENOORD, rating, minimum_for_rating(rating)),
            )
            player_id = int(cursor.lastrowid)
        _upsert_attributes(conn, player_id, FEYENOORD_DATA[name])
        changed += 1

    conn.execute(
        "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
        "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
        (FEYENOORD, COUNTRY),
    )
    if "deleted_teams" in roster_base._tables(conn):
        conn.execute("DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE", (FEYENOORD,))
    conn.execute("INSERT OR IGNORE INTO seed_state (key) VALUES (?)", (MIGRATION_MARKER,))
    return changed


def apply_feyenoord_json(runtime):
    if getattr(runtime, "_ajap_feyenoord_json", False):
        return
    base_db = runtime.db
    synced_guilds = set()

    def feyenoord_synced_db():
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
                    f"AJAP Feyenoord cargado: guild={guild_id} • "
                    f"{len(FEYENOORD_ROSTER)} jugadores desde Feyenoord.json"
                )
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = feyenoord_synced_db
    runtime._ajap_feyenoord_json = True
    print(
        f"AJAP migración Feyenoord activa: {len(FEYENOORD_ROSTER)} jugadores • "
        "OVR AJPA de 3 stats"
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_feyenoord(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_feyenoord_json(runtime)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_feyenoord_json_wrapped",
    False,
):
    _apply_guild_isolation_then_feyenoord._ajap_feyenoord_json_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_feyenoord


OVR_BY_PLAYER = {name: rating for name, _position, rating in FEYENOORD_ROSTER}
print(f"AJAP Feyenoord JSON listo: {len(FEYENOORD_ROSTER)} jugadores")
