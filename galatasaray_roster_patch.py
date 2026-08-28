"""Load Galatasaray squad data with full PES6 stats and AJAP OVR."""

from __future__ import annotations

import json
from pathlib import Path

import fiorentina_roster_patch as roster_base
import team_assignment as teams

GALATASARAY = "Galatasaray"
COUNTRY = "Turquía"
MIGRATION_MARKER = "galatasaray_json_v1_ovr3_20260827"
SOURCE = "Galatasaray.json • OVR AJPA promedio de 3 stats • 2026-08-27"
DATA_DIR = Path(__file__).resolve().parent / "data"
SOURCE_PARTS = tuple(DATA_DIR / f"Galatasaray.json.part{index:02d}" for index in range(1, 6))

POSITION_BY_PLAYER = {'Hasan Sas': 'LMF/WF',
 'Necati Ates': 'CF/SS',
 'Umit Karan': 'CF',
 'Cafercan Aksu': 'CF/SS',
 'Heinz': 'AMF/SS',
 'Hakan Sukur': 'CF',
 'Hasan Kabze': 'CF/SS',
 'Ozgurcan Ozcan': 'CF',
 'Cihan H': 'DMF/RB',
 'Volkan Arslan': 'CMF/DMF',
 'Sasa Llic': 'AMF/CMF',
 'Sabri': 'RMF/RB',
 'Ergun Penbe': 'LB/LMF',
 'Mehmet Guven': 'DMF/CMF',
 'Mulayim Erdem': 'CMF/LMF',
 'Ayhan Akman': 'CMF/DMF',
 'Aydin Yilmaz': 'RMF/WF',
 'Zafer Sakar': 'CMF/AMF',
 'Inamoto': 'DMF/CMF',
 'Arda Turan': 'AMF/WF',
 'Song': 'CB',
 'Tomas': 'CB',
 'Orhan Ak': 'LB/CB',
 'Yalcin Ayhan': 'CB',
 'Ugur Ucar': 'RB/RMF',
 'Emre Asik': 'CB',
 'Emrah Umut': 'CF/SS',
 'Tolga Seyhan': 'CB',
 'Ferhat Oztorun': 'LB',
 'Mondragon': 'GK',
 'Aykuy Ercetin': 'GK',
 'Fevzi Elmas': 'GK'}

STAT_MAP = roster_base.STAT_MAP
ATTR_COLUMNS = roster_base.ATTR_COLUMNS


def _load_source():
    payload = json.loads("".join(path.read_text(encoding="utf-8") for path in SOURCE_PARTS))
    if str(payload.get("equipo", "")).strip().casefold() != GALATASARAY.casefold():
        raise ValueError("Galatasaray.json no corresponde a Galatasaray")
    players = payload.get("jugadores") or []
    by_name = {str(player["nombre"]).strip(): player for player in players}
    if len(players) != len(POSITION_BY_PLAYER) or set(by_name) != set(POSITION_BY_PLAYER):
        missing = sorted(set(POSITION_BY_PLAYER) - set(by_name))
        extra = sorted(set(by_name) - set(POSITION_BY_PLAYER))
        raise ValueError(
            f"Galatasaray.json inválido: jugadores={len(players)} "
            f"faltan={missing or '-'} sobran={extra or '-'}"
        )
    return by_name


GALATASARAY_DATA = _load_source()


def _rating(position, stats):
    return roster_base._rating(position, stats)


GALATASARAY_ROSTER = [
    (name, POSITION_BY_PLAYER[name], _rating(POSITION_BY_PLAYER[name], GALATASARAY_DATA[name]["stats"]))
    for name in POSITION_BY_PLAYER
]

if not any(name.casefold() == GALATASARAY.casefold() for name, _country in teams.OFFICIAL_TEAMS):
    teams.OFFICIAL_TEAMS.append((GALATASARAY, COUNTRY))
teams.OFFICIAL[GALATASARAY.casefold()] = GALATASARAY


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
    names = [name for name, _position, _rating_value in GALATASARAY_ROSTER]
    marks = ",".join("?" for _ in names)
    present = conn.execute(
        f"SELECT COUNT(*) AS n FROM roster_players WHERE name COLLATE NOCASE IN ({marks})",
        tuple(names),
    ).fetchone()
    if int(present["n"] if present else 0) < len(GALATASARAY_ROSTER):
        conn.execute("DELETE FROM seed_state WHERE key = ?", (MIGRATION_MARKER,))

    done = conn.execute("SELECT 1 FROM seed_state WHERE key = ?", (MIGRATION_MARKER,)).fetchone()
    if done:
        conn.execute(
            "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
            "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
            (GALATASARAY, COUNTRY),
        )
        return 0

    changed = 0
    for name, position, rating in GALATASARAY_ROSTER:
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
                (name, position, GALATASARAY, rating, minimum_for_rating(rating)),
            )
            player_id = int(cursor.lastrowid)
        _upsert_attributes(conn, player_id, GALATASARAY_DATA[name])
        changed += 1

    conn.execute(
        "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
        "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
        (GALATASARAY, COUNTRY),
    )
    if "deleted_teams" in roster_base._tables(conn):
        conn.execute("DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE", (GALATASARAY,))
    conn.execute("INSERT OR IGNORE INTO seed_state (key) VALUES (?)", (MIGRATION_MARKER,))
    return changed


def apply_galatasaray_json(runtime):
    if getattr(runtime, "_ajap_galatasaray_json", False):
        return
    base_db = runtime.db
    synced_guilds = set()

    def galatasaray_synced_db():
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
                    f"AJAP Galatasaray cargado: guild={guild_id} • "
                    f"{len(GALATASARAY_ROSTER)} jugadores desde Galatasaray.json"
                )
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = galatasaray_synced_db
    runtime._ajap_galatasaray_json = True
    print(
        f"AJAP migración Galatasaray activa: {len(GALATASARAY_ROSTER)} jugadores • "
        "OVR AJPA de 3 stats"
    )


OVR_BY_PLAYER = {name: rating for name, _position, rating in GALATASARAY_ROSTER}
print(f"AJAP Galatasaray JSON listo: {len(GALATASARAY_ROSTER)} jugadores")
