"""Replace Villarreal's legacy AJAP roster from data/Villareal.json.

The uploaded JSON is the source of truth for canonical player names, full PES6
attributes and special abilities. Existing player IDs, transfers and current
clubs are preserved whenever the same player already exists. OVR is recalculated
with AJAP's current simple average of the 3 position-specific key stats.

The bot keeps the internal team key "Villarreal" for backwards compatibility
with existing assignments and market history, while accepting "Villarreal CF"
as the source label in the JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import guild_isolation_patch as guild_isolation
import multi_team_extension as multi


VILLARREAL = "Villarreal"
MIGRATION_MARKER = "villarreal_json_v1_ovr3_selector_repair_20260826"
SOURCE = "Villareal.json • OVR AJPA promedio de 3 stats • 2026-08-26"
SOURCE_PATH = Path(__file__).resolve().parent / "data" / "Villareal.json"

POSITION_BY_PLAYER = {
    "José Mari": "CF/SS",
    "Diego Forlán": "CF/SS",
    "Nihat Kahveci": "CF/SS",
    "Jonathan": "CF/SS",
    "Franco": "CF",
    "Marcos Senna": "DMF/CMF",
    "Cani": "RMF/AMF",
    "Robert Pires": "LMF/AMF",
    "Juan Román Riquelme": "AMF",
    "Alessio Tacchinardi": "DMF/CMF",
    "Josico": "DMF/CMF",
    "Marcos": "LMF/WF",
    "David Fuster": "AMF/LMF/RMF",
    "Sorin": "LB/LMF",
    "G. Rodriguez": "CB",
    "Quique Alvarez": "CB",
    "Javi Venta": "RB",
    "Arruabarrena": "LB/CB",
    "Peña": "CB",
    "Josemi": "RB/CB",
    "Jose Enrique": "LB",
    "Viera": "GK",
    "Barbosa": "GK",
    "Juan Carlos": "GK",
}

# Legacy AJAP names -> canonical names supplied in Villareal.json.
OLD_NAMES = {
    "Jonathan": ("Jonathan Pereira",),
    "Franco": ("Guillermo Franco", "Guille Franco"),
    "Robert Pires": ("Robert Pirès",),
    "Marcos": ("Marquitos", "Marcos García"),
    "Sorin": ("Juan Pablo Sorín", "Juan Pablo Sorin"),
    "G. Rodriguez": ("Gonzalo Rodríguez", "Gonzalo Rodriguez"),
    "Quique Alvarez": ("Quique Álvarez",),
    "Arruabarrena": ("Rodolfo Arruabarrena",),
    "Peña": ("Juan Manuel Peña",),
    "Jose Enrique": ("José Enrique",),
    "Viera": ("Sebastián Viera", "Sebastian Viera"),
    "Barbosa": ("Mariano Barbosa",),
}

# Players from the old 26-player seed that are intentionally not present in the
# uploaded 24-player JSON. They are removed only if they are still at Villarreal;
# already-transferred players stay untouched so market history remains valid.
LEGACY_ONLY_PLAYERS = (
    "Fabricio Fuentes",
    "Leandro Somoza",
    "Pascal Cygan",
    "Óscar López",
)

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
    source_team = str(payload.get("equipo", "")).strip().casefold()
    if source_team not in {"villarreal", "villarreal cf", "villareal", "villareal cf"}:
        raise ValueError("Villareal.json no corresponde a Villarreal CF")

    players = payload.get("jugadores") or []
    if len(players) != 24:
        raise ValueError(f"Villareal.json debe contener 24 jugadores; contiene {len(players)}")

    by_name = {str(player["nombre"]).strip(): player for player in players}
    expected = set(POSITION_BY_PLAYER)
    actual = set(by_name)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(
            "Villareal.json no coincide con la plantilla AJAP esperada "
            f"(faltan={missing or '-'}; sobran={extra or '-'})"
        )
    return by_name


VILLARREAL_DATA = _load_source()


def _aerial(stats):
    return int(round((int(stats["cabezazo"]) + int(stats["salto"])) / 2))


def _role_values(position: str, stats):
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
        raise RuntimeError(f"Posición Villarreal sin fórmula OVR: {position}")
    return tuple(int(value) for value in values)


def _rating(position: str, stats) -> int:
    values = _role_values(position, stats)
    return int(round(sum(values) / 3))


VILLARREAL_ROSTER = [
    (
        name,
        POSITION_BY_PLAYER[name],
        _rating(POSITION_BY_PLAYER[name], VILLARREAL_DATA[name]["stats"]),
    )
    for name in POSITION_BY_PLAYER
]

# Fresh databases seed the canonical 24-player roster immediately.
multi.VILLARREAL_ROSTER = list(VILLARREAL_ROSTER)


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


def _tables(conn):
    return [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]


def _rename_text_references(conn, old_name: str, new_name: str):
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


def _find_player(conn, canonical: str):
    candidates = (*OLD_NAMES.get(canonical, ()), canonical)
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


def _canonical_players_present(conn) -> int:
    names = [name for name, _position, _rating_value in VILLARREAL_ROSTER]
    marks = ",".join("?" for _ in names)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM roster_players WHERE name COLLATE NOCASE IN ({marks})",
        tuple(names),
    ).fetchone()
    return int(row["n"] if row else 0)


def _remove_legacy_only_players(conn):
    tables = set(_tables(conn))
    removed = 0
    for name in LEGACY_ONLY_PLAYERS:
        row = conn.execute(
            """
            SELECT id FROM roster_players
            WHERE name = ? COLLATE NOCASE AND club = ? COLLATE NOCASE
            LIMIT 1
            """,
            (name, VILLARREAL),
        ).fetchone()
        if not row:
            continue
        player_id = int(row["id"])
        if "publications" in tables:
            conn.execute(
                "UPDATE publications SET active = 0 WHERE player = ? COLLATE NOCASE",
                (name,),
            )
        if "pes6_player_special_abilities" in tables:
            conn.execute(
                "DELETE FROM pes6_player_special_abilities WHERE player_id = ?",
                (player_id,),
            )
        if "pes6_player_attributes" in tables:
            conn.execute(
                "DELETE FROM pes6_player_attributes WHERE player_id = ?",
                (player_id,),
            )
        conn.execute("DELETE FROM roster_players WHERE id = ?", (player_id,))
        removed += 1
    return removed


def _sync_connection(runtime, conn):
    from lyon_test_seed import minimum_for_rating

    _ensure_schema(runtime, conn)

    present = _canonical_players_present(conn)
    if present < len(VILLARREAL_ROSTER):
        conn.execute("DELETE FROM seed_state WHERE key = ?", (MIGRATION_MARKER,))

    done = conn.execute(
        "SELECT 1 FROM seed_state WHERE key = ?",
        (MIGRATION_MARKER,),
    ).fetchone()
    if done:
        conn.execute(
            """
            INSERT INTO league_teams (name, country, active)
            VALUES (?, 'España', 1)
            ON CONFLICT(name) DO UPDATE SET country = 'España', active = 1
            """,
            (VILLARREAL,),
        )
        return 0

    updated = 0
    for canonical, position, rating in VILLARREAL_ROSTER:
        payload = VILLARREAL_DATA[canonical]
        row, matched_name = _find_player(conn, canonical)

        if row:
            player_id = int(row["id"])
            if matched_name != canonical:
                _rename_text_references(conn, matched_name, canonical)
            # Do not change club: already-transferred players stay where they are.
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
                    VILLARREAL,
                    rating,
                    minimum_for_rating(rating),
                ),
            )
            player_id = int(cursor.lastrowid)

        _upsert_attributes(conn, player_id, payload)
        updated += 1

    removed = _remove_legacy_only_players(conn)

    conn.execute(
        """
        INSERT INTO league_teams (name, country, active)
        VALUES (?, 'España', 1)
        ON CONFLICT(name) DO UPDATE SET country = 'España', active = 1
        """,
        (VILLARREAL,),
    )

    if "deleted_teams" in set(_tables(conn)):
        conn.execute(
            "DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE",
            (VILLARREAL,),
        )

    conn.execute("INSERT INTO seed_state (key) VALUES (?)", (MIGRATION_MARKER,))
    return updated + removed


def apply_villarreal_json_replacement(runtime):
    if getattr(runtime, "_ajap_villarreal_json_replacement", False):
        return

    base_db = runtime.db
    synced_guilds = set()

    def villarreal_synced_db():
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
                    f"AJAP Villarreal reemplazado: guild={guild_id} • "
                    f"migración aplicada desde Villareal.json"
                )
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = villarreal_synced_db
    runtime._ajap_villarreal_json_replacement = True
    print(
        "AJAP migración Villarreal activa: Villareal.json • "
        "24 jugadores • OVR AJPA de 3 stats"
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_villarreal(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_villarreal_json_replacement(runtime)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_villarreal_json_replacement_wrapped",
    False,
):
    _apply_guild_isolation_then_villarreal._ajap_villarreal_json_replacement_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_villarreal


OVR_BY_PLAYER = {name: rating for name, _position, rating in VILLARREAL_ROSTER}

print(
    "AJAP Villarreal JSON listo: promedio simple de 3 stats por posición • "
    f"{len(VILLARREAL_ROSTER)} jugadores"
)
