"""One-time Real Betis replacement from data/Betis.json.

The uploaded JSON is the new source of truth for Betis PES6 attributes. Existing
player IDs, transfers and current clubs are preserved: only canonical names,
static position/OVR metadata and PES6 attributes are refreshed.
"""

from __future__ import annotations

import json
from pathlib import Path

import guild_isolation_patch as guild_isolation
import multi_team_extension as multi


BETIS = "Real Betis"
MARKER = "real_betis_json_v2_20260826"
SOURCE = "Betis.json • reemplazo 2026-08-26"
SOURCE_PATH = Path(__file__).resolve().parent / "data" / "Betis.json"

# The JSON contains the PES6 attributes but not AJAP positions/OVR. Keep the
# already-approved AJAP position and OVR for the same 24 Betis players.
BETIS_ROSTER = [
    ("Odonkor", "RMF/WF", 79),
    ("Rafael Sobis", "SS/CF", 81),
    ("Robert", "CF", 79),
    ("Dani", "CF", 76),
    ("Maldonado", "CF/SS", 73),
    ("Xisco", "CF/LMF", 75),
    ("Marcos Assuncao", "DMF/CMF", 84),
    ("Vogel", "DMF/CMF", 82),
    ("Edu", "AMF/LMF/SS", 82),
    ("Arzu", "DMF/CMF", 77),
    ("Miguel Angel", "DMF/CMF", 76),
    ("Rivera", "CMF", 78),
    ("Damia", "RMF/RB", 74),
    ("Fernando", "AMF/CMF", 78),
    ("Capi", "AMF", 80),
    ("Rivas", "CB", 77),
    ("Juanito", "CB", 81),
    ("Melli", "CB/RB", 76),
    ("Romero", "LB", 77),
    ("Lembo", "CB", 78),
    ("Nano", "CB", 74),
    ("Fernando Vega", "LB", 72),
    ("Doblas", "GK", 77),
    ("Contreras", "GK", 80),
]

# Previous AJAP names -> canonical names supplied in Betis.json.
OLD_NAMES = {
    "Odonkor": ("David Odonkor",),
    "Rafael Sobis": ("Rafael Sóbis",),
    "Robert": ("Robert de Pinho",),
    "Marcos Assuncao": ("Marcos Assunção",),
    "Vogel": ("Johann Vogel",),
    "Miguel Angel": ("Miguel Ángel",),
    "Rivera": ("Alberto Rivera",),
    "Damia": ("Damià",),
    "Rivas": ("David Rivas",),
    "Romero": ("Enrique Romero",),
    "Lembo": ("Alejandro Lembo",),
    "Doblas": ("Antonio Doblas",),
    "Contreras": ("Pedro Contreras",),
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

ATTR_COLUMNS = [
    "attack", "defence", "body_balance", "stamina", "top_speed",
    "acceleration", "response", "agility", "dribble_accuracy",
    "dribble_speed", "short_pass_accuracy", "short_pass_speed",
    "long_pass_accuracy", "long_pass_speed", "shot_accuracy", "shot_power",
    "shot_technique", "free_kick_accuracy", "curling", "header", "jump",
    "technique", "aggression", "mentality", "gk_skills", "teamwork",
    "injury_resistance", "weak_foot_usage", "weak_foot_accuracy",
]


def _load_source():
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if str(payload.get("equipo", "")).strip().casefold() != BETIS.casefold():
        raise ValueError("Betis.json no corresponde a Real Betis")
    players = payload.get("jugadores") or []
    if len(players) != 24:
        raise ValueError(f"Betis.json debe contener 24 jugadores; contiene {len(players)}")
    return {str(player["nombre"]).strip(): player for player in players}


BETIS_DATA = _load_source()
ROSTER_META = {name: (position, rating) for name, position, rating in BETIS_ROSTER}

# Fresh databases must seed the new canonical names immediately instead of the
# older long-name Betis list from multi_team_extension.py.
multi.REAL_BETIS_ROSTER = list(BETIS_ROSTER)


def _ensure_schema(runtime, conn):
    runtime.add_column_if_missing(conn, "roster_players", "rating", "INTEGER")
    runtime.add_column_if_missing(conn, "roster_players", "min_sale_value", "INTEGER")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seed_state (
            key TEXT PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pes6_player_attributes (
            player_id INTEGER PRIMARY KEY,
            attack INTEGER,
            defence INTEGER,
            body_balance INTEGER,
            stamina INTEGER,
            top_speed INTEGER,
            acceleration INTEGER,
            response INTEGER,
            agility INTEGER,
            dribble_accuracy INTEGER,
            dribble_speed INTEGER,
            short_pass_accuracy INTEGER,
            short_pass_speed INTEGER,
            long_pass_accuracy INTEGER,
            long_pass_speed INTEGER,
            shot_accuracy INTEGER,
            shot_power INTEGER,
            shot_technique INTEGER,
            free_kick_accuracy INTEGER,
            curling INTEGER,
            header INTEGER,
            jump INTEGER,
            technique INTEGER,
            aggression INTEGER,
            mentality INTEGER,
            gk_skills INTEGER,
            teamwork INTEGER,
            injury_resistance TEXT,
            weak_foot_usage INTEGER,
            weak_foot_accuracy INTEGER,
            source TEXT NOT NULL DEFAULT 'PES 6 original',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "injury_resistance", "TEXT")
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "weak_foot_usage", "INTEGER")
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "weak_foot_accuracy", "INTEGER")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pes6_player_special_abilities (
            player_id INTEGER NOT NULL,
            ability TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'PES 6 original',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (player_id, ability)
        )
        """
    )


def _tables(conn):
    return [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]


def _rename_text_references(conn, old_name: str, new_name: str):
    """Keep text-based market/history references consistent after canonical rename."""
    if old_name.casefold() == new_name.casefold():
        return
    for table in _tables(conn):
        if table == "roster_players":
            continue
        safe_table = table.replace('"', '""')
        for column in conn.execute(f'PRAGMA table_info("{safe_table}")').fetchall():
            column_name = str(column["name"])
            column_type = str(column["type"] or "").upper()
            if "PLAYER" not in column_name.upper() or "TEXT" not in column_type:
                continue
            safe_column = column_name.replace('"', '""')
            conn.execute(
                f'UPDATE "{safe_table}" SET "{safe_column}" = ? '
                f'WHERE "{safe_column}" = ? COLLATE NOCASE',
                (new_name, old_name),
            )


def _find_player(conn, canonical: str):
    candidates = (canonical, *OLD_NAMES.get(canonical, ()))
    for candidate in candidates:
        row = conn.execute(
            "SELECT * FROM roster_players WHERE name = ? COLLATE NOCASE LIMIT 1",
            (candidate,),
        ).fetchone()
        if row:
            return row, candidate
    return None, None


def _upsert_attributes(conn, player_id: int, player_payload):
    raw = player_payload.get("stats") or {}
    values = {target: raw.get(source) for source, target in STAT_MAP.items()}
    insert_columns = ["player_id", *ATTR_COLUMNS, "source", "updated_at"]
    placeholders = ["?" for _ in insert_columns[:-1]] + ["CURRENT_TIMESTAMP"]
    params = [player_id, *[values.get(column) for column in ATTR_COLUMNS], SOURCE]
    updates = [f"{column} = excluded.{column}" for column in ATTR_COLUMNS]
    updates.extend(["source = excluded.source", "updated_at = CURRENT_TIMESTAMP"])
    conn.execute(
        f"INSERT INTO pes6_player_attributes ({', '.join(insert_columns)}) "
        f"VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT(player_id) DO UPDATE SET {', '.join(updates)}",
        params,
    )

    conn.execute(
        "DELETE FROM pes6_player_special_abilities WHERE player_id = ?",
        (player_id,),
    )
    for ability in player_payload.get("habilidades_especiales") or []:
        conn.execute(
            """
            INSERT OR IGNORE INTO pes6_player_special_abilities
                (player_id, ability, source)
            VALUES (?, ?, ?)
            """,
            (player_id, str(ability).strip(), SOURCE),
        )


def _sync_connection(runtime, conn):
    from lyon_test_seed import minimum_for_rating

    _ensure_schema(runtime, conn)
    done = conn.execute(
        "SELECT 1 FROM seed_state WHERE key = ?",
        (MARKER,),
    ).fetchone()
    if done:
        return 0

    updated = 0
    for canonical, position, rating in BETIS_ROSTER:
        payload = BETIS_DATA.get(canonical)
        if not payload:
            raise ValueError(f"Falta {canonical} en Betis.json")

        row, matched_name = _find_player(conn, canonical)
        if row:
            player_id = int(row["id"])
            if matched_name != canonical:
                _rename_text_references(conn, matched_name, canonical)
            conn.execute(
                """
                UPDATE roster_players
                SET name = ?, position = ?, rating = ?, min_sale_value = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    canonical,
                    position,
                    rating,
                    minimum_for_rating(rating),
                    player_id,
                ),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO roster_players
                    (name, position, club, added_by, rating, min_sale_value, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    canonical,
                    position,
                    BETIS,
                    rating,
                    minimum_for_rating(rating),
                ),
            )
            player_id = int(cursor.lastrowid)

        _upsert_attributes(conn, player_id, payload)
        updated += 1

    # Keep the team active without touching who currently manages it.
    tables = set(_tables(conn))
    if "league_teams" in tables:
        conn.execute(
            """
            INSERT INTO league_teams (name, country, active)
            VALUES (?, 'España', 1)
            ON CONFLICT(name) DO UPDATE SET country = 'España', active = 1
            """,
            (BETIS,),
        )

    conn.execute("INSERT INTO seed_state (key) VALUES (?)", (MARKER,))
    return updated


def apply_betis_replacement(runtime):
    if getattr(runtime, "_ajap_betis_replacement", False):
        return

    base_db = runtime.db
    synced_guilds = set()

    def betis_synced_db():
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
                    f"AJAP Betis reemplazado: guild={guild_id} • "
                    f"{changed} jugadores + stats PES6 desde Betis.json"
                )
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = betis_synced_db
    runtime._ajap_betis_replacement = True
    print("AJAP migración Betis activa: Betis.json es la fuente de verdad")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_betis(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_betis_replacement(runtime)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_betis_replacement_wrapped",
    False,
):
    _apply_guild_isolation_then_betis._ajap_betis_replacement_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_betis
