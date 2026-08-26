"""Real Betis PES6 replacement sourced from the uploaded Betis.json.

Runs once per Discord guild DB. It refreshes static player metadata, recalculates
OVR with AJAP's current 3-stat-by-position formula, and stores all PES6 stats.
Completed transfers are preserved: existing players keep their current club.
"""

from __future__ import annotations

import json

import guild_isolation_patch as guild_isolation

BETIS = "Real Betis"
MIGRATION_KEY = "real_betis_betis_json_20260826_v1"

PLAYER_MAP = {
    "Odonkor": ("David Odonkor", "RMF/WF"),
    "Rafael Sobis": ("Rafael Sóbis", "SS/CF"),
    "Robert": ("Robert de Pinho", "CF"),
    "Dani": ("Dani", "CF"),
    "Maldonado": ("Maldonado", "CF/SS"),
    "Xisco": ("Xisco", "CF/LMF"),
    "Marcos Assuncao": ("Marcos Assunção", "DMF/CMF"),
    "Vogel": ("Johann Vogel", "DMF/CMF"),
    "Edu": ("Edu", "AMF/LMF/SS"),
    "Arzu": ("Arzu", "DMF/CMF"),
    "Miguel Angel": ("Miguel Ángel", "DMF/CMF"),
    "Rivera": ("Alberto Rivera", "CMF"),
    "Damia": ("Damià", "RMF/RB"),
    "Fernando": ("Fernando", "AMF/CMF"),
    "Capi": ("Capi", "AMF"),
    "Rivas": ("David Rivas", "CB"),
    "Juanito": ("Juanito", "CB"),
    "Melli": ("Melli", "CB/RB"),
    "Romero": ("Enrique Romero", "LB"),
    "Lembo": ("Alejandro Lembo", "CB"),
    "Nano": ("Nano", "CB"),
    "Fernando Vega": ("Fernando Vega", "LB"),
    "Doblas": ("Antonio Doblas", "GK"),
    "Contreras": ("Pedro Contreras", "GK"),
}

STAT_KEYS = ('ataque', 'defensa', 'equilibrio', 'resistencia', 'velocidad_maxima', 'aceleracion', 'respuesta', 'agilidad', 'precision_regate', 'velocidad_regate', 'precision_pase_corto', 'velocidad_pase_corto', 'precision_pase_largo', 'velocidad_pase_largo', 'precision_tiro', 'potencia_disparo', 'tecnica_disparo', 'saque_falta', 'efecto', 'cabezazo', 'salto', 'tecnica', 'agresividad', 'mentalidad', 'cualidad_portero', 'juego_equipo', 'resistencia_lesiones', 'uso_pie_malo', 'precision_pie_malo')
BETIS_DATA = [
    ('Odonkor', (76, 45, 78, 93, 97, 96, 80, 88, 82, 93, 74, 75, 71, 70, 70, 79, 71, 65, 72, 65, 72, 80, 75, 78, 50, 77, 'B', 6, 6), ('Velocidad',)),
    ('Rafael Sobis', (81, 35, 79, 82, 83, 84, 82, 82, 83, 82, 78, 77, 74, 73, 82, 85, 83, 81, 82, 72, 75, 85, 76, 80, 50, 80, 'B', 7, 7), ('Disparo lejano', 'Lanzamiento de faltas')),
    ('Robert', (78, 36, 77, 81, 84, 85, 79, 81, 80, 83, 75, 74, 70, 69, 79, 82, 80, 72, 75, 70, 74, 81, 74, 77, 50, 76, 'B', 6, 6), ('Velocidad',)),
    ('Dani', (76, 34, 76, 79, 80, 81, 77, 78, 77, 78, 74, 73, 68, 67, 77, 79, 78, 70, 72, 73, 75, 78, 73, 76, 50, 75, 'B', 6, 6), ()),
    ('Maldonado', (72, 42, 73, 78, 81, 82, 74, 77, 75, 79, 71, 70, 67, 66, 72, 75, 73, 66, 69, 64, 68, 75, 71, 72, 50, 72, 'B', 6, 6), ()),
    ('Xisco', (77, 38, 80, 80, 82, 81, 78, 76, 76, 77, 74, 73, 69, 68, 78, 83, 79, 68, 71, 80, 81, 77, 78, 77, 50, 76, 'B', 6, 6), ('Poder aéreo',)),
    ('Marcos Assuncao', (78, 68, 82, 83, 75, 76, 81, 77, 80, 77, 86, 85, 88, 87, 80, 92, 81, 96, 94, 70, 72, 87, 78, 84, 50, 86, 'A', 7, 7), ('Lanzamiento de faltas', 'Disparo lejano', 'Línea de pase')),
    ('Vogel', (72, 79, 83, 86, 76, 75, 82, 74, 77, 75, 84, 83, 82, 81, 68, 79, 69, 72, 74, 73, 75, 81, 80, 85, 50, 87, 'A', 6, 6), ('Línea de pase',)),
    ('Edu', (81, 52, 81, 85, 80, 81, 83, 80, 82, 81, 83, 82, 79, 78, 80, 83, 81, 76, 79, 76, 78, 85, 75, 83, 50, 85, 'A', 7, 7), ('Posicionamiento', 'Disparo lejano')),
    ('Arzu', (73, 74, 80, 86, 77, 78, 78, 75, 76, 75, 78, 77, 76, 75, 71, 78, 72, 68, 71, 77, 80, 78, 82, 80, 50, 81, 'A', 6, 6), ()),
    ('Miguel Angel', (71, 72, 78, 84, 78, 79, 76, 76, 75, 74, 77, 76, 75, 74, 69, 76, 70, 67, 70, 72, 75, 76, 79, 78, 50, 79, 'B', 6, 6), ()),
    ('Rivera', (74, 73, 79, 85, 77, 78, 78, 77, 78, 77, 80, 79, 78, 77, 70, 77, 71, 71, 73, 70, 73, 80, 77, 80, 50, 82, 'A', 6, 6), ()),
    ('Damia', (72, 74, 77, 86, 85, 86, 76, 80, 76, 81, 75, 74, 72, 71, 68, 75, 69, 64, 68, 69, 73, 77, 79, 78, 50, 79, 'B', 6, 6), ('Velocidad',)),
    ('Fernando', (73, 76, 78, 84, 80, 81, 78, 77, 77, 79, 76, 75, 75, 74, 70, 77, 71, 68, 72, 73, 76, 78, 81, 80, 50, 80, 'A', 6, 6), ()),
    ('Capi', (75, 60, 76, 83, 79, 81, 79, 82, 81, 80, 80, 79, 77, 76, 74, 78, 75, 73, 76, 65, 69, 83, 75, 80, 50, 82, 'B', 7, 7), ('Regate',)),
    ('Rivas', (62, 82, 84, 82, 76, 75, 81, 71, 68, 67, 74, 73, 76, 75, 55, 78, 56, 58, 60, 84, 86, 72, 85, 82, 50, 80, 'A', 5, 5), ('Poder aéreo', 'Línea defensiva')),
    ('Juanito', (65, 85, 86, 84, 75, 74, 84, 73, 72, 71, 78, 77, 81, 80, 58, 80, 59, 65, 67, 87, 89, 77, 86, 87, 50, 85, 'A', 6, 6), ('Línea defensiva', 'Poder aéreo', 'Línea de pase')),
    ('Melli', (63, 81, 83, 83, 78, 77, 81, 74, 70, 69, 75, 74, 76, 75, 56, 77, 57, 59, 61, 83, 85, 74, 83, 82, 50, 81, 'A', 5, 5), ('Poder aéreo',)),
    ('Romero', (64, 80, 82, 81, 74, 73, 80, 70, 69, 68, 76, 75, 77, 76, 57, 76, 58, 62, 64, 81, 83, 73, 82, 83, 50, 80, 'B', 5, 5), ()),
    ('Lembo', (61, 80, 86, 80, 72, 71, 79, 68, 66, 65, 72, 71, 74, 73, 54, 79, 55, 57, 59, 86, 88, 70, 87, 80, 50, 78, 'B', 5, 5), ('Poder aéreo', 'Luchador')),
    ('Nano', (66, 78, 79, 83, 79, 80, 77, 75, 72, 74, 74, 73, 73, 72, 60, 75, 61, 61, 64, 75, 78, 75, 81, 79, 50, 78, 'A', 6, 6), ()),
    ('Fernando Vega', (68, 77, 78, 85, 80, 81, 78, 76, 73, 75, 76, 75, 76, 75, 62, 76, 63, 70, 73, 71, 74, 76, 80, 80, 50, 80, 'A', 6, 6), ()),
    ('Doblas', (50, 84, 82, 73, 66, 66, 90, 77, 52, 50, 63, 65, 74, 80, 40, 83, 42, 48, 47, 50, 84, 55, 74, 82, 87, 78, 'A', 5, 5), ()),
    ('Contreras', (50, 81, 79, 71, 64, 64, 87, 74, 49, 47, 60, 62, 71, 77, 37, 80, 39, 45, 44, 47, 80, 52, 71, 79, 84, 75, 'B', 5, 5), ()),
]

STAT_TO_COLUMN = {
    "ataque": "attack", "defensa": "defence", "equilibrio": "body_balance",
    "resistencia": "stamina", "velocidad_maxima": "top_speed", "aceleracion": "acceleration",
    "respuesta": "response", "agilidad": "agility", "precision_regate": "dribble_accuracy",
    "velocidad_regate": "dribble_speed", "precision_pase_corto": "short_pass_accuracy",
    "velocidad_pase_corto": "short_pass_speed", "precision_pase_largo": "long_pass_accuracy",
    "velocidad_pase_largo": "long_pass_speed", "precision_tiro": "shot_accuracy",
    "potencia_disparo": "shot_power", "tecnica_disparo": "shot_technique",
    "saque_falta": "free_kick_accuracy", "efecto": "curling", "cabezazo": "header",
    "salto": "jump", "tecnica": "technique", "agresividad": "aggression",
    "mentalidad": "mentality", "cualidad_portero": "gk_skills", "juego_equipo": "teamwork",
}
STANDARD_ATTRIBUTE_COLUMNS = tuple(STAT_TO_COLUMN.values())


def _players():
    result = []
    for name, raw_values, skills in BETIS_DATA:
        stats = dict(zip(STAT_KEYS, raw_values))
        result.append({"nombre": name, "stats": stats, "habilidades_especiales": list(skills)})
    if len(result) != 24 or {p["nombre"] for p in result} != set(PLAYER_MAP):
        raise RuntimeError("Datos embebidos del Betis incompletos")
    return result


BETIS_PLAYERS = _players()


def _aerial(stats):
    return int(round((int(stats["cabezazo"]) + int(stats["salto"])) / 2))


def _role_values(position: str, stats):
    primary = str(position or "").upper().replace(" ", "").split("/", 1)[0]
    aerial = _aerial(stats)
    values = {
        "GK": (("Reflejos", stats["respuesta"]), ("Atajadas", stats["cualidad_portero"]), ("Colocación", stats["defensa"])),
        "CB": (("Defensa", stats["defensa"]), ("Fuerza", stats["equilibrio"]), ("Juego aéreo", aerial)),
        "LB": (("Defensa", stats["defensa"]), ("Velocidad", stats["velocidad_maxima"]), ("Resistencia", stats["resistencia"])),
        "RB": (("Defensa", stats["defensa"]), ("Velocidad", stats["velocidad_maxima"]), ("Resistencia", stats["resistencia"])),
        "DMF": (("Defensa", stats["defensa"]), ("Pase", stats["precision_pase_corto"]), ("Resistencia", stats["resistencia"])),
        "CMF": (("Pase", stats["precision_pase_corto"]), ("Técnica", stats["tecnica"]), ("Resistencia", stats["resistencia"])),
        "AMF": (("Pase", stats["precision_pase_corto"]), ("Regate", stats["precision_regate"]), ("Tiro", stats["precision_tiro"])),
        "LMF": (("Velocidad", stats["velocidad_maxima"]), ("Regate", stats["precision_regate"]), ("Pase", stats["precision_pase_corto"])),
        "RMF": (("Velocidad", stats["velocidad_maxima"]), ("Regate", stats["precision_regate"]), ("Pase", stats["precision_pase_corto"])),
        "WF": (("Velocidad", stats["velocidad_maxima"]), ("Regate", stats["precision_regate"]), ("Tiro", stats["precision_tiro"])),
        "SS": (("Regate", stats["precision_regate"]), ("Pase", stats["precision_pase_corto"]), ("Tiro", stats["precision_tiro"])),
        "CF": (("Tiro", stats["precision_tiro"]), ("Ataque", stats["ataque"]), ("Juego aéreo", aerial)),
    }.get(primary)
    if values is None:
        raise RuntimeError(f"Posición Betis sin fórmula OVR: {position}")
    return tuple((name, int(value)) for name, value in values)


def _rating(position, stats):
    values = _role_values(position, stats)
    return int(round(sum(value for _, value in values) / 3))


def _ensure_schema(runtime, conn):
    runtime.add_column_if_missing(conn, "roster_players", "rating", "INTEGER")
    runtime.add_column_if_missing(conn, "roster_players", "min_sale_value", "INTEGER")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS seed_state (key TEXT PRIMARY KEY, applied_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS league_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            country TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pes6_player_attributes (
            player_id INTEGER PRIMARY KEY, attack INTEGER, defence INTEGER, body_balance INTEGER, stamina INTEGER,
            top_speed INTEGER, acceleration INTEGER, response INTEGER, agility INTEGER, dribble_accuracy INTEGER,
            dribble_speed INTEGER, short_pass_accuracy INTEGER, short_pass_speed INTEGER, long_pass_accuracy INTEGER,
            long_pass_speed INTEGER, shot_accuracy INTEGER, shot_power INTEGER, shot_technique INTEGER,
            free_kick_accuracy INTEGER, curling INTEGER, header INTEGER, jump INTEGER, technique INTEGER,
            aggression INTEGER, mentality INTEGER, gk_skills INTEGER, teamwork INTEGER,
            source TEXT NOT NULL DEFAULT 'PES 6 original', updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS player_rating_inputs (
            player_id INTEGER PRIMARY KEY, position_key TEXT NOT NULL, stat_1_name TEXT NOT NULL, stat_1_value INTEGER NOT NULL,
            stat_2_name TEXT NOT NULL, stat_2_value INTEGER NOT NULL, stat_3_name TEXT NOT NULL, stat_3_value INTEGER NOT NULL,
            calculated_ovr INTEGER NOT NULL, formula TEXT NOT NULL DEFAULT 'PROMEDIO_SIMPLE_3', created_by INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "injury_resistance", "TEXT")
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "weak_foot_usage", "INTEGER")
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "weak_foot_accuracy", "INTEGER")
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "special_abilities_json", "TEXT")


def _find_player(conn, canonical_name, source_name):
    row = conn.execute("SELECT id,name,club FROM roster_players WHERE name=? COLLATE NOCASE LIMIT 1", (canonical_name,)).fetchone()
    if row or source_name.casefold() == canonical_name.casefold():
        return row
    return conn.execute("SELECT id,name,club FROM roster_players WHERE name=? COLLATE NOCASE LIMIT 1", (source_name,)).fetchone()


def _upsert_attributes(conn, player_id, stats, skills):
    vals = {column: int(stats[source]) for source, column in STAT_TO_COLUMN.items()}
    columns = ["player_id", *STANDARD_ATTRIBUTE_COLUMNS, "injury_resistance", "weak_foot_usage",
               "weak_foot_accuracy", "special_abilities_json", "source", "updated_at"]
    placeholders = ["?" for _ in columns[:-1]] + ["CURRENT_TIMESTAMP"]
    params = [int(player_id), *[vals[c] for c in STANDARD_ATTRIBUTE_COLUMNS],
              str(stats.get("resistencia_lesiones") or "").strip() or None,
              int(stats["uso_pie_malo"]), int(stats["precision_pie_malo"]),
              json.dumps(skills or [], ensure_ascii=False), "Betis.json • PES6"]
    updates = [f"{c}=excluded.{c}" for c in columns[1:-1]] + ["updated_at=CURRENT_TIMESTAMP"]
    conn.execute(
        f"INSERT INTO pes6_player_attributes ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT(player_id) DO UPDATE SET {', '.join(updates)}", params
    )


def _sync_connection(runtime, conn):
    from lyon_test_seed import minimum_for_rating
    _ensure_schema(runtime, conn)
    if conn.execute("SELECT 1 FROM seed_state WHERE key=?", (MIGRATION_KEY,)).fetchone():
        return 0
    conn.execute("""INSERT INTO league_teams(name,country,active) VALUES(?,'España',1)
        ON CONFLICT(name) DO UPDATE SET country=excluded.country,active=1""", (BETIS,))
    migrated = 0
    for src in BETIS_PLAYERS:
        source_name = src["nombre"]
        canonical_name, position = PLAYER_MAP[source_name]
        stats, skills = src["stats"], src["habilidades_especiales"]
        rating = _rating(position, stats)
        minimum = minimum_for_rating(rating)
        row = _find_player(conn, canonical_name, source_name)
        if row is None:
            cur = conn.execute("""INSERT INTO roster_players(name,position,club,added_by,rating,min_sale_value,updated_at)
                VALUES(?,?,?,NULL,?,?,CURRENT_TIMESTAMP)""", (canonical_name, position, BETIS, rating, minimum))
            player_id = int(cur.lastrowid)
        else:
            player_id = int(row["id"])
            if str(row["name"]).casefold() != canonical_name.casefold():
                conflict = conn.execute("SELECT id FROM roster_players WHERE name=? COLLATE NOCASE AND id!=? LIMIT 1", (canonical_name, player_id)).fetchone()
                if not conflict:
                    conn.execute("UPDATE roster_players SET name=? WHERE id=?", (canonical_name, player_id))
            conn.execute("UPDATE roster_players SET position=?,rating=?,min_sale_value=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (position, rating, minimum, player_id))
        role = _role_values(position, stats)
        position_key = position.upper().replace(" ", "").split("/", 1)[0]
        conn.execute("""INSERT INTO player_rating_inputs(
                player_id,position_key,stat_1_name,stat_1_value,stat_2_name,stat_2_value,stat_3_name,stat_3_value,
                calculated_ovr,formula,created_by,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,'PROMEDIO_SIMPLE_3_PES6_JSON',NULL,CURRENT_TIMESTAMP)
            ON CONFLICT(player_id) DO UPDATE SET position_key=excluded.position_key,stat_1_name=excluded.stat_1_name,
                stat_1_value=excluded.stat_1_value,stat_2_name=excluded.stat_2_name,stat_2_value=excluded.stat_2_value,
                stat_3_name=excluded.stat_3_name,stat_3_value=excluded.stat_3_value,calculated_ovr=excluded.calculated_ovr,
                formula=excluded.formula,updated_at=CURRENT_TIMESTAMP""",
            (player_id, position_key, role[0][0], role[0][1], role[1][0], role[1][1], role[2][0], role[2][1], rating))
        _upsert_attributes(conn, player_id, stats, skills)
        migrated += 1
    conn.execute("INSERT INTO seed_state(key) VALUES(?)", (MIGRATION_KEY,))
    return migrated


def apply_betis_roster_replace(runtime):
    if getattr(runtime, "_ajap_betis_roster_replace", False):
        return
    base_db = runtime.db
    synced_guilds = set()
    def betis_synced_db():
        conn = base_db()
        guild_id = int(runtime.current_guild_id())
        if guild_id in synced_guilds:
            return conn
        try:
            migrated = _sync_connection(runtime, conn)
            conn.commit()
            synced_guilds.add(guild_id)
            if migrated:
                print(f"AJAP Betis.json aplicado: guild={guild_id} jugadores={migrated}")
        except Exception:
            conn.close()
            raise
        return conn
    runtime.db = betis_synced_db
    runtime._ajap_betis_roster_replace = True
    print("AJAP sync Betis.json activo: 24 jugadores + OVR + stats PES6 completas")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch

def _apply_guild_isolation_then_betis(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_betis_roster_replace(runtime)

if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_betis_roster_replace_wrapped", False):
    _apply_guild_isolation_then_betis._ajap_betis_roster_replace_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_betis
