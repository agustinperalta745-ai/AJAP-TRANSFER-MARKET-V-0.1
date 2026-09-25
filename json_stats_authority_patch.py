"""Make team JSON files the single authority for PES6 player stats.

This patch intentionally changes ONLY persisted PES6 attributes and special
abilities. It never changes a player's current club, transfer history, offers,
position, AJPA OVR or minimum sale value.

Every process restart re-applies the JSON values on first access to each guild DB,
so legacy/imported/hardcoded PES6 values cannot win over the supplied JSON files.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

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
ATTR_COLUMNS = tuple(STAT_MAP.values())


def _norm(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _json_sources():
    for path in sorted(DATA_DIR.glob("*.json"), key=lambda p: p.name.casefold()):
        yield path.name, json.loads(path.read_text(encoding="utf-8"))

    multipart = {}
    for part in DATA_DIR.glob("*.json.part*"):
        prefix, sep, suffix = part.name.rpartition(".part")
        if sep and prefix.casefold().endswith(".json") and suffix.isdigit():
            multipart.setdefault(prefix, []).append((int(suffix), part))

    for prefix in sorted(multipart, key=str.casefold):
        parts = sorted(multipart[prefix], key=lambda item: item[0])
        text = "".join(path.read_text(encoding="utf-8") for _idx, path in parts)
        yield f"{prefix}.part*", json.loads(text)


def _ensure_schema(runtime, conn):
    runtime.add_column_if_missing(conn, "roster_players", "rating", "INTEGER")
    runtime.add_column_if_missing(conn, "roster_players", "min_sale_value", "INTEGER")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pes6_player_attributes (
            player_id INTEGER PRIMARY KEY,
            attack INTEGER, defence INTEGER, body_balance INTEGER,
            stamina INTEGER, top_speed INTEGER, acceleration INTEGER,
            response INTEGER, agility INTEGER, dribble_accuracy INTEGER,
            dribble_speed INTEGER, short_pass_accuracy INTEGER,
            short_pass_speed INTEGER, long_pass_accuracy INTEGER,
            long_pass_speed INTEGER, shot_accuracy INTEGER,
            shot_power INTEGER, shot_technique INTEGER,
            free_kick_accuracy INTEGER, curling INTEGER, header INTEGER,
            jump INTEGER, technique INTEGER, aggression INTEGER,
            mentality INTEGER, gk_skills INTEGER, teamwork INTEGER,
            injury_resistance TEXT, weak_foot_usage INTEGER,
            weak_foot_accuracy INTEGER,
            source TEXT NOT NULL DEFAULT 'AJPA JSON',
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
            source TEXT NOT NULL DEFAULT 'AJPA JSON',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (player_id, ability)
        )
        """
    )


def _db_player_index(conn):
    rows = conn.execute("SELECT id, name, club FROM roster_players ORDER BY id").fetchall()
    exact = {}
    normalized = {}
    for row in rows:
        name = str(row["name"] or "").strip()
        exact.setdefault(name.casefold(), []).append(row)
        normalized.setdefault(_norm(name), []).append(row)
    return exact, normalized


def _resolve_player(name, exact, normalized):
    direct = exact.get(str(name).strip().casefold(), [])
    if len(direct) == 1:
        return direct[0]
    relaxed = normalized.get(_norm(name), [])
    if len(relaxed) == 1:
        return relaxed[0]
    return None


def _upsert_exact(conn, player_id: int, stats: dict, abilities, source: str):
    values = {target: stats.get(source_key) for source_key, target in STAT_MAP.items()}
    columns = ["player_id", *ATTR_COLUMNS, "source", "updated_at"]
    placeholders = ["?" for _ in columns[:-1]] + ["CURRENT_TIMESTAMP"]
    params = [int(player_id), *[values[column] for column in ATTR_COLUMNS], source]
    updates = [f"{column}=excluded.{column}" for column in ATTR_COLUMNS]
    updates += ["source=excluded.source", "updated_at=CURRENT_TIMESTAMP"]
    conn.execute(
        f"INSERT INTO pes6_player_attributes ({', '.join(columns)}) "
        f"VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT(player_id) DO UPDATE SET {', '.join(updates)}",
        params,
    )

    conn.execute("DELETE FROM pes6_player_special_abilities WHERE player_id=?", (int(player_id),))
    for ability in abilities or []:
        text = str(ability).strip()
        if text:
            conn.execute(
                "INSERT OR IGNORE INTO pes6_player_special_abilities "
                "(player_id, ability, source) VALUES (?, ?, ?)",
                (int(player_id), text, source),
            )


def _verify_one(conn, player_id: int, stats: dict, abilities):
    row = conn.execute(
        "SELECT * FROM pes6_player_attributes WHERE player_id=? LIMIT 1",
        (int(player_id),),
    ).fetchone()
    if row is None:
        return False

    for source_key, column in STAT_MAP.items():
        expected = stats.get(source_key)
        actual = row[column] if column in row.keys() else None
        if actual != expected:
            return False

    actual_abilities = [
        str(r["ability"])
        for r in conn.execute(
            "SELECT ability FROM pes6_player_special_abilities "
            "WHERE player_id=? ORDER BY rowid",
            (int(player_id),),
        ).fetchall()
    ]
    expected_abilities = [str(a).strip() for a in (abilities or []) if str(a).strip()]
    return actual_abilities == expected_abilities


def _sync_connection(runtime, conn):
    _ensure_schema(runtime, conn)
    exact, normalized = _db_player_index(conn)

    synced = 0
    verified = 0
    unmatched = []
    duplicate_resolutions = []
    candidates_by_player = {}

    for source_label, payload in _json_sources():
        team = str(payload.get("equipo") or "").strip()
        players = payload.get("jugadores") or []
        if not isinstance(players, list):
            continue

        for item in players:
            name = str(item.get("nombre") or "").strip()
            if not name:
                continue
            row = _resolve_player(name, exact, normalized)
            if row is None:
                unmatched.append(f"{team}: {name}")
                continue

            player_id = int(row["id"])
            candidates_by_player.setdefault(player_id, []).append(
                (row, team, source_label, item)
            )

    def _club_key(value):
        key = _norm(value)
        aliases = {
            "sevillafc": "sevilla",
            "sevilla": "sevilla",
            "olympiquedemarsella": "olympiquedemarsella",
            "marsella": "olympiquedemarsella",
            "villarrealcf": "villarreal",
            "villarealcf": "villarreal",
            "villareal": "villarreal",
            "villarreal": "villarreal",
        }
        return aliases.get(key, key)

    for player_id, candidates in candidates_by_player.items():
        chosen = candidates[0]
        if len(candidates) > 1:
            current_club = str(candidates[0][0]["club"] or "")
            club_matches = [
                candidate for candidate in candidates
                if _club_key(candidate[1]) == _club_key(current_club)
            ]
            if len(club_matches) == 1:
                chosen = club_matches[0]
                reason = "club_actual"
            else:
                # The historical schema has UNIQUE(name), so two JSON players with
                # exactly the same display name cannot coexist as separate rows yet.
                # Never blend their stats: keep one complete JSON record atomically.
                reason = "sin_match_unico"
            duplicate_resolutions.append(
                f"{chosen[3].get('nombre')} -> {chosen[1]} "
                f"(club DB={current_club or '-'}, {reason})"
            )

        row, team, source_label, item = chosen
        stats = item.get("stats") or {}
        abilities = item.get("habilidades_especiales") or []
        source = f"AJPA JSON autoritativo • {source_label}"
        _upsert_exact(conn, player_id, stats, abilities, source)
        synced += 1
        if _verify_one(conn, player_id, stats, abilities):
            verified += 1

    if duplicate_resolutions:
        print(
            "AJPA JSON stats: nombres duplicados resueltos sin mezclar stats -> "
            + " | ".join(duplicate_resolutions[:20])
        )
    if unmatched:
        print(
            f"WARNING AJPA JSON stats: {len(unmatched)} jugador(es) no encontrados -> "
            + " | ".join(unmatched[:30])
        )

    if verified != synced:
        raise RuntimeError(
            f"AJPA JSON stats verification failed: synced={synced} verified={verified}"
        )

    print(
        f"AJPA JSON STATS AUTORITATIVAS OK: synced={synced} verified={verified} "
        f"unmatched={len(unmatched)} duplicate_names={len(duplicate_resolutions)}"
    )
    return synced


def apply_json_stats_authority(runtime):
    if getattr(runtime, "_ajpa_json_stats_authority", False):
        return

    base_db = runtime.db
    synced_guilds = set()

    def authoritative_db():
        conn = base_db()
        try:
            guild_id = int(runtime.current_guild_id())
        except Exception:
            guild_id = 0
        if guild_id in synced_guilds:
            return conn
        try:
            _sync_connection(runtime, conn)
            conn.commit()
            synced_guilds.add(guild_id)
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = authoritative_db

    # Force the official/current DB to be repaired immediately at startup,
    # before Discord connects.
    conn = runtime.db()
    conn.close()

    runtime._ajpa_json_stats_authority = True
    print("AJPA JSON stats authority installed: JSON wins over every legacy source")
