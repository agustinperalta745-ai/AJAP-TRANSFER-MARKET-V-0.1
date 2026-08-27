"""Replace Tottenham Hotspur's legacy AJAP roster from data/Tottenham Hotspur.json.

The uploaded JSON is the source of truth for canonical player names, full PES6
attributes and special abilities. Existing player IDs, transfers and current
clubs are preserved whenever the same legacy player already exists. OVR is
recalculated with AJAP's current simple average of 3 position-specific key stats.
"""

from __future__ import annotations

import json
from pathlib import Path

import guild_isolation_patch as guild_isolation
import multi_team_extension as multi


TOTTENHAM = "Tottenham Hotspur"
COUNTRY = "Inglaterra"
MIGRATION_MARKER = "tottenham_hotspur_json_v1_ovr3_20260827"
SOURCE = "Tottenham Hotspur.json • OVR AJPA promedio de 3 stats • 2026-08-27"
SOURCE_PATH = Path(__file__).resolve().parent / "data" / "Tottenham Hotspur.json"

POSITION_BY_PLAYER = {'Berbatov': 'CF',
 'Robbie Keane': 'SS/CF',
 'Defoe': 'CF',
 'Routledge': 'RMF/SMF',
 'Lee Barnard': 'CF',
 'Mido': 'CF',
 'Stalteri': 'RB/LB',
 'Zokora': 'DMF/CMF',
 'Jenas': 'CMF/AMF',
 'Lennon': 'RMF/SMF',
 'Davids': 'CMF/DMF',
 'Danny Murphy': 'AMF/CMF',
 'Huddlestone': 'CMF/DMF',
 'Reto Ziegler': 'LMF/LB',
 'Ghaly': 'CMF/DMF',
 'Tainio': 'CMF/DMF',
 'O´Hara': 'CMF/LMF',
 'Dawson': 'CB',
 'King': 'CB',
 'Y.P. Lee': 'LB',
 'Gardner': 'CB',
 'Davenport': 'CB',
 'Assou Ekotto': 'LB',
 'Ifil': 'RB',
 'Chimbonda': 'RB',
 'Robinson': 'GK',
 'Cerny': 'GK',
 'Fulop': 'GK'}

# Legacy AJAP names -> canonical names supplied in Tottenham Hotspur.json.
OLD_NAMES = {'Berbatov': ('Dimitar Berbatov',),
 'Defoe': ('Jermain Defoe',),
 'Routledge': ('Wayne Routledge',),
 'Stalteri': ('Paul Stalteri',),
 'Zokora': ('Didier Zokora',),
 'Jenas': ('Jermaine Jenas',),
 'Lennon': ('Aaron Lennon',),
 'Davids': ('Edgar Davids',),
 'Huddlestone': ('Tom Huddlestone',),
 'Ghaly': ('Hossam Ghaly',),
 'Tainio': ('Teemu Tainio',),
 'O´Hara': ("Jamie O'Hara", 'Jamie O´Hara'),
 'Dawson': ('Michael Dawson',),
 'King': ('Ledley King',),
 'Y.P. Lee': ('Lee Young-Pyo', 'Young-Pyo Lee'),
 'Gardner': ('Anthony Gardner',),
 'Davenport': ('Calum Davenport',),
 'Assou Ekotto': ('Benoît Assou-Ekotto', 'Benoit Assou-Ekotto'),
 'Ifil': ('Philip Ifil',),
 'Chimbonda': ('Pascal Chimbonda',),
 'Robinson': ('Paul Robinson',),
 'Cerny': ('Radek Černý', 'Radek Cerny'),
 'Fulop': ('Márton Fülöp', 'Marton Fulop')}

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
    if str(payload.get("equipo", "")).strip().casefold() != TOTTENHAM.casefold():
        raise ValueError("Tottenham Hotspur.json no corresponde a Tottenham Hotspur")

    players = payload.get("jugadores") or []
    by_name = {str(player["nombre"]).strip(): player for player in players}
    expected = set(POSITION_BY_PLAYER)
    actual = set(by_name)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if len(players) != 28 or missing or extra:
        raise ValueError(
            "Tottenham Hotspur.json inválido: "
            f"jugadores={len(players)} faltan={missing or '-'} sobran={extra or '-'}"
        )
    return by_name


TOTTENHAM_DATA = _load_source()


def _aerial(stats):
    return int(round((int(stats["cabezazo"]) + int(stats["salto"])) / 2))


def _role_values(position, stats):
    primary = str(position or "").upper().replace(" ", "").split("/", 1)[0]
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
        raise RuntimeError(f"Posición Tottenham Hotspur sin fórmula OVR: {position}")
    return tuple(int(value) for value in values)


def _rating(position, stats):
    values = _role_values(position, stats)
    return int(round(sum(values) / 3))


TOTTENHAM_ROSTER = [
    (name, POSITION_BY_PLAYER[name], _rating(POSITION_BY_PLAYER[name], TOTTENHAM_DATA[name]["stats"]))
    for name in POSITION_BY_PLAYER
]

# Fresh guild databases seed the canonical JSON roster immediately instead of
# the old full-name Tottenham list from multi_team_extension.
multi.TOTTENHAM_ROSTER = list(TOTTENHAM_ROSTER)


def _tables(conn):
    return [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS league_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            country TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _rename_text_references(conn, old_name, new_name):
    if old_name.casefold() == new_name.casefold():
        return

    for table in _tables(conn):
        if table in {"roster_players", "pes6_player_attributes", "pes6_player_special_abilities"}:
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


def _find_player(conn, canonical):
    candidates = (*OLD_NAMES.get(canonical, ()), canonical)
    for candidate in candidates:
        row = conn.execute(
            "SELECT * FROM roster_players WHERE name = ? COLLATE NOCASE LIMIT 1",
            (candidate,),
        ).fetchone()
        if row:
            return row, candidate
    return None, None


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
            """
            INSERT OR IGNORE INTO pes6_player_special_abilities
                (player_id, ability, source)
            VALUES (?, ?, ?)
            """,
            (player_id, str(ability).strip(), SOURCE),
        )


def _canonical_players_present(conn):
    names = [name for name, _position, _rating_value in TOTTENHAM_ROSTER]
    marks = ",".join("?" for _ in names)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM roster_players WHERE name COLLATE NOCASE IN ({marks})",
        tuple(names),
    ).fetchone()
    return int(row["n"] if row else 0)


def _sync_connection(runtime, conn):
    from lyon_test_seed import minimum_for_rating

    _ensure_schema(runtime, conn)

    if _canonical_players_present(conn) < len(TOTTENHAM_ROSTER):
        conn.execute("DELETE FROM seed_state WHERE key = ?", (MIGRATION_MARKER,))

    done = conn.execute(
        "SELECT 1 FROM seed_state WHERE key = ?",
        (MIGRATION_MARKER,),
    ).fetchone()
    if done:
        conn.execute(
            """
            INSERT INTO league_teams (name, country, active)
            VALUES (?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1
            """,
            (TOTTENHAM, COUNTRY),
        )
        return 0

    changed = 0
    for canonical, position, rating in TOTTENHAM_ROSTER:
        payload = TOTTENHAM_DATA[canonical]
        row, matched_name = _find_player(conn, canonical)

        if row:
            player_id = int(row["id"])
            if matched_name != canonical:
                _rename_text_references(conn, matched_name, canonical)
            # Preserve current club: a Tottenham player already transferred remains
            # at his destination while receiving the canonical name/stats/OVR.
            conn.execute(
                """
                UPDATE roster_players
                SET name = ?, position = ?, rating = ?, min_sale_value = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (canonical, position, rating, minimum_for_rating(rating), player_id),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO roster_players
                    (name, position, club, added_by, rating, min_sale_value, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?, CURRENT_TIMESTAMP)
                """,
                (canonical, position, TOTTENHAM, rating, minimum_for_rating(rating)),
            )
            player_id = int(cursor.lastrowid)

        _upsert_attributes(conn, player_id, payload)
        changed += 1

    conn.execute(
        """
        INSERT INTO league_teams (name, country, active)
        VALUES (?, ?, 1)
        ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1
        """,
        (TOTTENHAM, COUNTRY),
    )
    if "deleted_teams" in set(_tables(conn)):
        conn.execute("DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE", (TOTTENHAM,))

    conn.execute("INSERT INTO seed_state (key) VALUES (?)", (MIGRATION_MARKER,))
    return changed


def apply_tottenham_hotspur_json_replacement(runtime):
    if getattr(runtime, "_ajap_tottenham_hotspur_json_replacement", False):
        return

    base_db = runtime.db
    synced_guilds = set()

    def tottenham_synced_db():
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
                    f"AJAP Tottenham Hotspur reemplazado: guild={guild_id} • "
                    "28 jugadores desde Tottenham Hotspur.json"
                )
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = tottenham_synced_db
    runtime._ajap_tottenham_hotspur_json_replacement = True
    print("AJAP migración Tottenham Hotspur activa: 28 jugadores • OVR AJPA de 3 stats")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_tottenham(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_tottenham_hotspur_json_replacement(runtime)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_tottenham_hotspur_json_replacement_wrapped",
    False,
):
    _apply_guild_isolation_then_tottenham._ajap_tottenham_hotspur_json_replacement_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_tottenham


OVR_BY_PLAYER = {name: rating for name, _position, rating in TOTTENHAM_ROSTER}
print(f"AJAP Tottenham Hotspur JSON listo: {len(TOTTENHAM_ROSTER)} jugadores")
