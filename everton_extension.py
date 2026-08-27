"""Load Everton from data/Everton.json with full PES6 stats and AJAP OVR.

This replaces the old 24-player hardcoded Everton seed. Existing legacy Everton
players are matched by alias and renamed in place so their player IDs are kept.
"""

from __future__ import annotations

import json
from pathlib import Path

import guild_isolation_patch as guild_isolation
import team_assignment as teams

EVERTON = "Everton"
COUNTRY = "Inglaterra"
MIGRATION_MARKER = "everton_json_v1_ovr3_alias_migration_20260827"
SOURCE = "Everton.json • OVR AJPA promedio de 3 stats • 2026-08-27"
SOURCE_PATH = Path(__file__).resolve().parent / "data" / "Everton.json"

POSITION_BY_PLAYER = {
    "Beattie": "CF",
    "Mcfadden": "SS",
    "Van der Meyde": "RMF",
    "Vaughan": "CF",
    "Andrew Johnson": "CF",
    "Anichebe": "CF",
    "Arteta": "CMF",
    "Cahill": "AMF",
    "Osman": "AMF",
    "Kilbane": "LMF",
    "Carsley": "DMF",
    "Simon Davies": "RMF",
    "Vidarsson": "CMF",
    "Weir": "CB",
    "Yobo": "CB",
    "Hibbert": "RB",
    "Nuno Valente": "LB",
    "P. Neville": "RB",
    "Stubbs": "CB",
    "Mark Hughes": "CB",
    "Lescott": "CB",
    "Naysmith": "LB",
    "Pistone": "LB",
    "Boyle": "LB",
    "Howard": "GK",
    "Wright": "GK",
    "Turner": "GK",
    "Ruddy": "GK",
}

# Names used by the previous hardcoded Everton seed. These aliases let the JSON
# migration preserve player IDs instead of creating duplicate players.
LEGACY_NAME_BY_PLAYER = {
    "Beattie": "James Beattie",
    "Mcfadden": "James McFadden",
    "Van der Meyde": "Andy van der Meyde",
    "Vaughan": "James Vaughan",
    "Andrew Johnson": "Andrew Johnson",
    "Anichebe": "Victor Anichebe",
    "Arteta": "Mikel Arteta",
    "Cahill": "Tim Cahill",
    "Osman": "Leon Osman",
    "Carsley": "Lee Carsley",
    "Simon Davies": "Simon Davies",
    "Weir": "David Weir",
    "Yobo": "Joseph Yobo",
    "Hibbert": "Tony Hibbert",
    "Nuno Valente": "Nuno Valente",
    "P. Neville": "Phil Neville",
    "Stubbs": "Alan Stubbs",
    "Lescott": "Joleon Lescott",
    "Naysmith": "Gary Naysmith",
    "Pistone": "Alessandro Pistone",
    "Howard": "Tim Howard",
    "Wright": "Richard Wright",
    "Turner": "Iain Turner",
    "Ruddy": "John Ruddy",
}

STAT_MAP = {
    "ataque": "attack",
    "defensa": "defence",
    "equilibrio": "body_balance",
    "resistencia": "stamina",
    "velocidad_maxima": "top_speed",
    "aceleracion": "acceleration",
    "respuesta": "response",
    "agilidad": "agility",
    "precision_regate": "dribble_accuracy",
    "velocidad_regate": "dribble_speed",
    "precision_pase_corto": "short_pass_accuracy",
    "velocidad_pase_corto": "short_pass_speed",
    "precision_pase_largo": "long_pass_accuracy",
    "velocidad_pase_largo": "long_pass_speed",
    "precision_tiro": "shot_accuracy",
    "potencia_disparo": "shot_power",
    "tecnica_disparo": "shot_technique",
    "saque_falta": "free_kick_accuracy",
    "efecto": "curling",
    "cabezazo": "header",
    "salto": "jump",
    "tecnica": "technique",
    "agresividad": "aggression",
    "mentalidad": "mentality",
    "cualidad_portero": "gk_skills",
    "juego_equipo": "teamwork",
    "resistencia_lesiones": "injury_resistance",
    "uso_pie_malo": "weak_foot_usage",
    "precision_pie_malo": "weak_foot_accuracy",
}
ATTR_COLUMNS = list(STAT_MAP.values())


def _load_source():
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if str(payload.get("equipo", "")).strip().casefold() != EVERTON.casefold():
        raise ValueError("Everton.json no corresponde a Everton")
    players = payload.get("jugadores") or []
    by_name = {str(player["nombre"]).strip(): player for player in players}
    if len(players) != 28 or set(by_name) != set(POSITION_BY_PLAYER):
        missing = sorted(set(POSITION_BY_PLAYER) - set(by_name))
        extra = sorted(set(by_name) - set(POSITION_BY_PLAYER))
        raise ValueError(
            f"Everton.json inválido: jugadores={len(players)} faltan={missing or '-'} sobran={extra or '-'}"
        )
    return by_name


EVERTON_DATA = _load_source()


def _aerial(stats):
    return int(round((int(stats["cabezazo"]) + int(stats["salto"])) / 2))


def _role_values(position, stats):
    primary = str(position).upper().replace(" ", "").split("/", 1)[0]
    aerial = _aerial(stats)
    values = {
        "GK": (stats["respuesta"], stats["cualidad_portero"], stats["defensa"]),
        "CB": (stats["defensa"], stats["equilibrio"], aerial),
        "LB": (stats["defensa"], stats["velocidad_maxima"], stats["resistencia"]),
        "RB": (stats["defensa"], stats["velocidad_maxima"], stats["resistencia"]),
        "DMF": (stats["defensa"], stats["precision_pase_corto"], stats["resistencia"]),
        "CMF": (stats["precision_pase_corto"], stats["tecnica"], stats["resistencia"]),
        "AMF": (stats["precision_pase_corto"], stats["precision_regate"], stats["precision_tiro"]),
        "LMF": (stats["velocidad_maxima"], stats["precision_regate"], stats["precision_pase_corto"]),
        "RMF": (stats["velocidad_maxima"], stats["precision_regate"], stats["precision_pase_corto"]),
        "WF": (stats["velocidad_maxima"], stats["precision_regate"], stats["precision_tiro"]),
        "SS": (stats["precision_regate"], stats["precision_pase_corto"], stats["precision_tiro"]),
        "CF": (stats["precision_tiro"], stats["ataque"], aerial),
    }.get(primary)
    if values is None:
        raise RuntimeError(f"Posición Everton sin fórmula OVR: {position}")
    return tuple(int(value) for value in values)


def _rating(position, stats):
    values = _role_values(position, stats)
    return int(round(sum(values) / 3))


EVERTON_ROSTER = [
    (name, POSITION_BY_PLAYER[name], _rating(POSITION_BY_PLAYER[name], EVERTON_DATA[name]["stats"]))
    for name in POSITION_BY_PLAYER
]

# Make Everton visible before Discord views are registered.
if not any(name.casefold() == EVERTON.casefold() for name, _country in teams.OFFICIAL_TEAMS):
    teams.OFFICIAL_TEAMS.append((EVERTON, COUNTRY))
teams.OFFICIAL[EVERTON.casefold()] = EVERTON


def _tables(conn):
    return {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


def _ensure_schema(runtime, conn):
    runtime.add_column_if_missing(conn, "roster_players", "rating", "INTEGER")
    runtime.add_column_if_missing(conn, "roster_players", "min_sale_value", "INTEGER")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS seed_state ("
        "key TEXT PRIMARY KEY, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pes6_player_attributes (
            player_id INTEGER PRIMARY KEY, attack INTEGER, defence INTEGER, body_balance INTEGER,
            stamina INTEGER, top_speed INTEGER, acceleration INTEGER, response INTEGER, agility INTEGER,
            dribble_accuracy INTEGER, dribble_speed INTEGER, short_pass_accuracy INTEGER,
            short_pass_speed INTEGER, long_pass_accuracy INTEGER, long_pass_speed INTEGER,
            shot_accuracy INTEGER, shot_power INTEGER, shot_technique INTEGER, free_kick_accuracy INTEGER,
            curling INTEGER, header INTEGER, jump INTEGER, technique INTEGER, aggression INTEGER,
            mentality INTEGER, gk_skills INTEGER, teamwork INTEGER, injury_resistance TEXT,
            weak_foot_usage INTEGER, weak_foot_accuracy INTEGER,
            source TEXT NOT NULL DEFAULT 'PES 6 original', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "injury_resistance", "TEXT")
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "weak_foot_usage", "INTEGER")
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "weak_foot_accuracy", "INTEGER")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pes6_player_special_abilities (
            player_id INTEGER NOT NULL, ability TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'PES 6 original', created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (player_id, ability)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS league_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            country TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


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


def _find_existing_player(conn, canonical_name):
    row = conn.execute(
        "SELECT id, name, club FROM roster_players WHERE name = ? COLLATE NOCASE LIMIT 1",
        (canonical_name,),
    ).fetchone()
    if row:
        return row

    legacy_name = LEGACY_NAME_BY_PLAYER.get(canonical_name)
    if not legacy_name or legacy_name.casefold() == canonical_name.casefold():
        return None

    row = conn.execute(
        "SELECT id, name, club FROM roster_players WHERE name = ? COLLATE NOCASE LIMIT 1",
        (legacy_name,),
    ).fetchone()
    if not row:
        return None

    # Rename the old hardcoded entry in place to preserve player_id/history links.
    conn.execute(
        "UPDATE roster_players SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (canonical_name, int(row["id"])),
    )
    return conn.execute(
        "SELECT id, name, club FROM roster_players WHERE id = ?",
        (int(row["id"]),),
    ).fetchone()


def _canonical_players_present(conn):
    names = [name for name, _position, _rating_value in EVERTON_ROSTER]
    marks = ",".join("?" for _ in names)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM roster_players WHERE name COLLATE NOCASE IN ({marks})",
        tuple(names),
    ).fetchone()
    return int(row["n"] if row else 0)


def _sync_connection(runtime, conn):
    from lyon_test_seed import minimum_for_rating

    _ensure_schema(runtime, conn)
    present = _canonical_players_present(conn)
    if present < len(EVERTON_ROSTER):
        conn.execute("DELETE FROM seed_state WHERE key = ?", (MIGRATION_MARKER,))

    done = conn.execute("SELECT 1 FROM seed_state WHERE key = ?", (MIGRATION_MARKER,)).fetchone()
    if done:
        conn.execute(
            "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
            "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
            (EVERTON, COUNTRY),
        )
        return 0

    changed = 0
    for name, position, rating in EVERTON_ROSTER:
        row = _find_existing_player(conn, name)
        if row:
            player_id = int(row["id"])
            current_club = str(row["club"] or "").strip()
            target_club = current_club or EVERTON
            conn.execute(
                "UPDATE roster_players SET position = ?, club = ?, rating = ?, min_sale_value = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (position, target_club, rating, minimum_for_rating(rating), player_id),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO roster_players "
                "(name, position, club, added_by, rating, min_sale_value, updated_at) "
                "VALUES (?, ?, ?, NULL, ?, ?, CURRENT_TIMESTAMP)",
                (name, position, EVERTON, rating, minimum_for_rating(rating)),
            )
            player_id = int(cursor.lastrowid)

        _upsert_attributes(conn, player_id, EVERTON_DATA[name])
        changed += 1

    conn.execute(
        "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
        "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
        (EVERTON, COUNTRY),
    )
    if "deleted_teams" in _tables(conn):
        conn.execute("DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE", (EVERTON,))
    conn.execute("INSERT INTO seed_state (key) VALUES (?)", (MIGRATION_MARKER,))
    return changed


def apply_everton_json(runtime):
    if getattr(runtime, "_ajap_everton_json", False):
        return

    base_db = runtime.db
    synced_guilds = set()

    def everton_synced_db():
        conn = base_db()
        guild_id = int(runtime.current_guild_id())
        if guild_id in synced_guilds:
            return conn
        try:
            changed = _sync_connection(runtime, conn)
            conn.commit()
            synced_guilds.add(guild_id)
            if changed:
                print(f"AJAP Everton cargado: guild={guild_id} • 28 jugadores desde Everton.json")
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = everton_synced_db
    runtime._ajap_everton_json = True
    print("AJAP migración Everton activa: 28 jugadores • OVR AJPA de 3 stats")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_everton(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_everton_json(runtime)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_everton_json_wrapped", False):
    _apply_guild_isolation_then_everton._ajap_everton_json_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_everton


OVR_BY_PLAYER = {name: rating for name, _position, rating in EVERTON_ROSTER}
print(f"AJAP Everton JSON listo: {len(EVERTON_ROSTER)} jugadores")
