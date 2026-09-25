"""Make SERA.xlsx the authority for AJPA PES6 player statistics.

This patch overwrites ONLY persisted PES6 attribute columns. It never changes
current club, transfers, purchases, sales, offers, roster position, AJPA OVR,
minimum sale value, or special abilities.

The compact payload in data/excel_stats_blob is generated from the user-supplied
SERA.xlsx workbook and is integrity-checked before any database write.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import re
import unicodedata
from pathlib import Path

BLOB_DIR = Path(__file__).resolve().parent / "data" / "excel_stats_blob"
EXPECTED_SHA256 = "dc201e5a6dd79c1484990a8c5af3e800af805f34b7fdb85e1b8872bdcf76d300"
EXPECTED_ROWS = 623
SOURCE_LABEL = "PES 6 original • SERA.xlsx"

ATTR_COLUMNS = (
    "attack", "defence", "body_balance", "stamina", "top_speed",
    "acceleration", "response", "agility", "dribble_accuracy",
    "dribble_speed", "short_pass_accuracy", "short_pass_speed",
    "long_pass_accuracy", "long_pass_speed", "shot_accuracy",
    "shot_power", "shot_technique", "free_kick_accuracy", "curling",
    "header", "jump", "technique", "aggression", "mentality",
    "gk_skills", "teamwork", "injury_resistance", "weak_foot_usage",
    "weak_foot_accuracy",
)

EXPECTED_COLUMNS = (
    "name", "team", "excel_name", *ATTR_COLUMNS,
)


def _norm(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _club_key(value) -> str:
    key = _norm(value)
    aliases = {
        "sevillafc": "sevilla",
        "sevilla": "sevilla",
        "olympiquedemarsella": "olympiquedemarsella",
        "olympiquedemarseille": "olympiquedemarsella",
        "marsella": "olympiquedemarsella",
        "marseille": "olympiquedemarsella",
        "villarrealcf": "villarreal",
        "villarealcf": "villarreal",
        "villareal": "villarreal",
        "villarreal": "villarreal",
        "atleticodemadrid": "atleticomadrid",
        "atleticomadrid": "atleticomadrid",
        "parissaintgermain": "psg",
        "psg": "psg",
        "asmonaco": "monaco",
        "monaco": "monaco",
        "olympiquedelyon": "lyon",
        "olympiquelyon": "lyon",
        "lyon": "lyon",
    }
    return aliases.get(key, key)


def _load_payload():
    parts = sorted(BLOB_DIR.glob("part*.txt"), key=lambda p: p.name)
    if len(parts) != 5:
        raise RuntimeError(f"SERA stats payload incomplete: expected 5 parts, found {len(parts)}")

    encoded = "".join(part.read_text(encoding="utf-8").strip() for part in parts)
    try:
        raw = gzip.decompress(base64.b64decode(encoded, validate=True))
    except Exception as exc:
        raise RuntimeError(f"SERA stats payload decode failed: {exc}") from exc

    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(
            f"SERA stats payload integrity failed: {digest} != {EXPECTED_SHA256}"
        )

    payload = json.loads(raw.decode("utf-8"))
    columns = tuple(payload.get("columns") or ())
    rows = payload.get("rows") or []

    if columns != EXPECTED_COLUMNS:
        raise RuntimeError("SERA stats payload columns do not match expected schema")
    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(
            f"SERA stats payload row count mismatch: {len(rows)} != {EXPECTED_ROWS}"
        )

    records = []
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(columns):
            raise RuntimeError(f"SERA stats payload malformed row {index}")
        records.append(dict(zip(columns, row)))
    return records


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
            source TEXT NOT NULL DEFAULT 'PES 6 original',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "injury_resistance", "TEXT")
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "weak_foot_usage", "INTEGER")
    runtime.add_column_if_missing(conn, "pes6_player_attributes", "weak_foot_accuracy", "INTEGER")


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


def _upsert_exact(conn, player_id: int, record: dict):
    columns = ["player_id", *ATTR_COLUMNS, "source", "updated_at"]
    placeholders = ["?" for _ in columns[:-1]] + ["CURRENT_TIMESTAMP"]
    params = [
        int(player_id),
        *[record.get(column) for column in ATTR_COLUMNS],
        SOURCE_LABEL,
    ]
    updates = [f"{column}=excluded.{column}" for column in ATTR_COLUMNS]
    updates += ["source=excluded.source", "updated_at=CURRENT_TIMESTAMP"]

    conn.execute(
        f"INSERT INTO pes6_player_attributes ({', '.join(columns)}) "
        f"VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT(player_id) DO UPDATE SET {', '.join(updates)}",
        params,
    )


def _verify_one(conn, player_id: int, record: dict):
    row = conn.execute(
        "SELECT * FROM pes6_player_attributes WHERE player_id=? LIMIT 1",
        (int(player_id),),
    ).fetchone()
    if row is None:
        return False
    for column in ATTR_COLUMNS:
        if row[column] != record.get(column):
            return False
    return str(row["source"] or "") == SOURCE_LABEL


def _sync_connection(runtime, conn):
    records = _load_payload()
    _ensure_schema(runtime, conn)
    exact, normalized = _db_player_index(conn)

    candidates_by_player = {}
    unmatched = []

    for record in records:
        row = _resolve_player(record["name"], exact, normalized)
        if row is None:
            unmatched.append(f"{record['team']}: {record['name']}")
            continue
        candidates_by_player.setdefault(int(row["id"]), []).append((row, record))

    synced = 0
    verified = 0
    duplicate_resolutions = []

    for player_id, candidates in candidates_by_player.items():
        chosen = candidates[0]
        if len(candidates) > 1:
            current_club = str(candidates[0][0]["club"] or "")
            club_matches = [
                candidate
                for candidate in candidates
                if _club_key(candidate[1]["team"]) == _club_key(current_club)
            ]
            if len(club_matches) == 1:
                chosen = club_matches[0]
                reason = "club_actual"
            else:
                # Legacy DB identity is UNIQUE(name). Never blend two players:
                # choose one complete source row atomically if current club cannot
                # disambiguate. Current AJPA production resolves every duplicate
                # through current club, so this branch is only a safety fallback.
                reason = "sin_match_unico"

            duplicate_resolutions.append(
                f"{chosen[1]['name']} -> {chosen[1]['team']} "
                f"(club DB={current_club or '-'}, {reason})"
            )

        _row, record = chosen
        _upsert_exact(conn, player_id, record)
        synced += 1
        if _verify_one(conn, player_id, record):
            verified += 1

    if unmatched:
        print(
            f"WARNING AJPA EXCEL stats: {len(unmatched)} jugador(es) no encontrados -> "
            + " | ".join(unmatched[:30])
        )
    if duplicate_resolutions:
        print(
            "AJPA EXCEL stats: nombres duplicados resueltos sin mezclar stats -> "
            + " | ".join(duplicate_resolutions[:20])
        )

    if unmatched:
        raise RuntimeError(
            f"AJPA EXCEL stats refused: {len(unmatched)} source player(s) unmatched"
        )
    if verified != synced:
        raise RuntimeError(
            f"AJPA EXCEL stats verification failed: synced={synced} verified={verified}"
        )

    print(
        f"AJPA EXCEL STATS AUTORITATIVAS OK: synced={synced} verified={verified} "
        f"unmatched={len(unmatched)} duplicate_names={len(duplicate_resolutions)} "
        f"source=SERA.xlsx"
    )
    return synced


def apply_excel_stats_authority(runtime):
    if getattr(runtime, "_ajpa_excel_stats_authority", False):
        return

    base_db = runtime.db
    synced_guilds = set()

    def authoritative_db():
        # base_db is the already-installed JSON wrapper, so legacy JSON sync
        # happens first. SERA.xlsx is then applied last and therefore wins.
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

    # Repair/verify the current official DB before Discord connects.
    conn = runtime.db()
    conn.close()

    runtime._ajpa_excel_stats_authority = True
    print("AJPA Excel stats authority installed: SERA.xlsx wins over JSON stats")
