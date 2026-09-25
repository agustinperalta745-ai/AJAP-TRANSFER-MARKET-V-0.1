"""SERA.xlsx is the single authority for AJPA PES6 player statistics.

Only persisted PES6 attributes and special abilities are changed.
Club ownership, transfers, offers, history, budgets, AJPA OVR and values are untouched.
"""

from __future__ import annotations

import base64
import difflib
import gzip
import json
import re
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
OFFICIAL_DATA = DATA_DIR / "official_pes6_sera_stats.b64"
EXPECTED_RECORDS = 617

BASE_COLUMNS = (
    "attack", "defence", "body_balance", "stamina", "top_speed",
    "acceleration", "response", "agility", "dribble_accuracy",
    "dribble_speed", "short_pass_accuracy", "short_pass_speed",
    "long_pass_accuracy", "long_pass_speed", "shot_accuracy",
    "shot_power", "shot_technique", "free_kick_accuracy", "curling",
    "header", "jump", "technique", "aggression", "mentality",
    "gk_skills", "teamwork",
)
EXTRA_COLUMNS = (
    "injury_resistance", "weak_foot_usage", "weak_foot_accuracy",
    "consistency", "condition_fitness",
)
ATTR_COLUMNS = BASE_COLUMNS + EXTRA_COLUMNS

TEAM_TO_PES_CLUB = {
    "Ajax": "Ajax",
    "Aston Villa": "West Midlands Village",
    "Atletico de Madrid": "C. Atlético Madrid",
    "Benfica": "Benfica",
    "Real Betis": "R. Betis",
    "Bolton Wanderers": "Middlebrook",
    "Everton": "Merseyside Blue",
    "Feyenoord": "Feyenoord",
    "Fiorentina": "Fiorentina",
    "Fulham": "West London White",
    "Galatasaray": "Galatasaray",
    "Lazio": "Lazio",
    "Olympique de Lyon": "Olympique Lyonnais",
    "Manchester City": "Man Blue",
    "Olympique de Marsella": "Olympique de Marseille",
    "Middlesbrough": "Teesside",
    "AS Monaco": "AS Monaco",
    "Paris Saint-Germain": "Paris Saint-Germain",
    "Porto": "FC Porto",
    "Sevilla FC": "Sevilla F.C.",
    "Tottenham Hotspur": "North East London",
    "Villarreal CF": "Villarreal C.F.",
    "West Ham United": "East London",
    "Real Zaragoza": "R. Zaragoza",
}

# The historical roster table uses UNIQUE(name), so these five display names
# collapsed multiple real PES6 players into one DB row. Railway logs from the
# last verified pre-cutover database establish which original AJPA player the
# surviving row represents. This prevents transfers from changing identity.
DUPLICATE_SOURCE_TEAM = {
    "cahill": "Everton",
    "leo": "Benfica",
    "gardner": "Bolton Wanderers",
    "walker": "West Ham United",
    "adriano": "Sevilla FC",
}


def _norm_words(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("´", "'")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _norm(value: object) -> str:
    return _norm_words(value).replace(" ", "")


def _core_tokens(value: object) -> list[str]:
    return [token for token in _norm_words(value).split() if len(token) > 1]


def _match_score(roster_name: str, pes_name: str) -> int:
    left = _norm_words(roster_name)
    right = _norm_words(pes_name)
    if not left or not right:
        return 0
    if left == right:
        return 100

    lc = left.replace(" ", "")
    rc = right.replace(" ", "")
    if lc == rc:
        return 100

    lt = _core_tokens(roster_name)
    rt = _core_tokens(pes_name)
    if lt and rt and lt == rt:
        return 98

    # Full-name vs surname-only / initials cases: Juan Román Riquelme -> Riquelme,
    # Djibril Cisse -> Cisse, M. Petrov -> Petrov, etc.
    if lt and rt:
        if len(lt) == 1 and lt[0] == rt[-1]:
            return 95
        if len(rt) == 1 and rt[0] == lt[-1]:
            return 95
        shorter, longer = (lt, rt) if len(lt) <= len(rt) else (rt, lt)
        if len(shorter) and longer[-len(shorter):] == shorter:
            return 94
        if set(shorter).issubset(set(longer)):
            return 92
        if lt[-1] == rt[-1]:
            return 88

    short, long = (lc, rc) if len(lc) <= len(rc) else (rc, lc)
    if len(short) >= 5 and (long.endswith(short) or short in long):
        return 86

    ratio = difflib.SequenceMatcher(None, lc, rc).ratio()
    if ratio >= 0.92:
        return 84
    if ratio >= 0.86:
        return 78
    if ratio >= 0.80:
        return 72
    return 0


def _load_official_payload() -> dict:
    encoded = "".join(OFFICIAL_DATA.read_text(encoding="utf-8").split())
    raw = gzip.decompress(base64.b64decode(encoded))
    payload = json.loads(raw.decode("utf-8"))
    records = payload.get("records") or []
    if len(records) != EXPECTED_RECORDS:
        raise RuntimeError(
            f"SERA stats payload invalid: expected={EXPECTED_RECORDS} got={len(records)}"
        )
    return payload


def _roster_sources():
    for path in sorted(DATA_DIR.glob("*.json"), key=lambda p: p.name.casefold()):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("jugadores"), list):
            yield path.name, payload

    multipart: dict[str, list[tuple[int, Path]]] = {}
    for part in DATA_DIR.glob("*.json.part*"):
        prefix, sep, suffix = part.name.rpartition(".part")
        if sep and prefix.casefold().endswith(".json") and suffix.isdigit():
            multipart.setdefault(prefix, []).append((int(suffix), part))
    for prefix in sorted(multipart, key=str.casefold):
        parts = sorted(multipart[prefix], key=lambda item: item[0])
        text = "".join(path.read_text(encoding="utf-8") for _idx, path in parts)
        payload = json.loads(text)
        if isinstance(payload, dict) and isinstance(payload.get("jugadores"), list):
            yield f"{prefix}.part*", payload


def build_identity_map() -> tuple[dict[str, dict], list[str]]:
    payload = _load_official_payload()
    by_club: dict[str, list[dict]] = {}
    for record in payload["records"]:
        by_club.setdefault(str(record["pes_club"]), []).append(record)

    candidates: dict[str, list[tuple[str, str, dict, int]]] = {}
    problems: list[str] = []

    for source_label, roster in _roster_sources():
        team = str(roster.get("equipo") or "").strip()
        pes_club = TEAM_TO_PES_CLUB.get(team)
        if not pes_club:
            continue
        official = by_club.get(pes_club, [])
        if not official:
            problems.append(f"{team}: no official club {pes_club}")
            continue

        for item in roster.get("jugadores") or []:
            db_name = str(item.get("nombre") or "").strip()
            if not db_name:
                continue
            scored = sorted(
                (
                    (_match_score(db_name, str(record["pes_name"])), record)
                    for record in official
                ),
                key=lambda pair: pair[0],
                reverse=True,
            )
            if not scored or scored[0][0] < 72:
                problems.append(f"{team}: no match for {db_name}")
                continue
            best_score, best = scored[0]
            second = scored[1][0] if len(scored) > 1 else -1
            if second == best_score and _norm(scored[1][1]["pes_name"]) != _norm(best["pes_name"]):
                problems.append(
                    f"{team}: ambiguous {db_name} -> {best['pes_name']} / {scored[1][1]['pes_name']}"
                )
                continue
            candidates.setdefault(_norm(db_name), []).append(
                (team, db_name, best, best_score)
            )

    identity: dict[str, dict] = {}
    for key, matches in candidates.items():
        if len(matches) == 1:
            identity[key] = matches[0][2]
            continue

        forced_team = DUPLICATE_SOURCE_TEAM.get(key)
        forced = [match for match in matches if match[0] == forced_team]
        if len(forced) == 1:
            identity[key] = forced[0][2]
            continue

        details = " | ".join(
            f"{team}:{db_name}->{record['pes_name']}[{score}]"
            for team, db_name, record, score in matches
        )
        problems.append(f"duplicate unresolved {key}: {details}")

    if len(identity) != EXPECTED_RECORDS:
        problems.append(
            f"identity count mismatch: expected={EXPECTED_RECORDS} got={len(identity)}"
        )
    return identity, problems


def _ensure_schema(runtime, conn):
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
            weak_foot_accuracy INTEGER, consistency INTEGER,
            condition_fitness INTEGER,
            source TEXT NOT NULL DEFAULT 'SERA.xlsx',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for name, type_name in (
        ("injury_resistance", "TEXT"),
        ("weak_foot_usage", "INTEGER"),
        ("weak_foot_accuracy", "INTEGER"),
        ("consistency", "INTEGER"),
        ("condition_fitness", "INTEGER"),
    ):
        runtime.add_column_if_missing(conn, "pes6_player_attributes", name, type_name)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pes6_player_special_abilities (
            player_id INTEGER NOT NULL,
            ability TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'SERA.xlsx',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (player_id, ability)
        )
        """
    )


def _db_player_index(conn):
    rows = conn.execute("SELECT id, name FROM roster_players ORDER BY id").fetchall()
    exact: dict[str, list] = {}
    normalized: dict[str, list] = {}
    for row in rows:
        name = str(row["name"] or "").strip()
        exact.setdefault(name.casefold(), []).append(row)
        normalized.setdefault(_norm(name), []).append(row)
    return exact, normalized


def _resolve_player(name: str, exact: dict, normalized: dict):
    direct = exact.get(name.casefold(), [])
    if len(direct) == 1:
        return direct[0]
    relaxed = normalized.get(_norm(name), [])
    if len(relaxed) == 1:
        return relaxed[0]
    return None


def _values_for_record(record: dict) -> dict:
    stats = dict(record.get("stats") or {})
    stats.update(
        injury_resistance=record.get("injury_resistance"),
        weak_foot_usage=record.get("weak_foot_usage"),
        weak_foot_accuracy=record.get("weak_foot_accuracy"),
        consistency=record.get("consistency"),
        condition_fitness=record.get("condition_fitness"),
    )
    return stats


def _upsert_exact(conn, player_id: int, record: dict):
    values = _values_for_record(record)
    source = f"SERA.xlsx · Sheet1 fila {int(record['source_row'])}"
    columns = ["player_id", *ATTR_COLUMNS, "source", "updated_at"]
    placeholders = ["?" for _ in columns[:-1]] + ["CURRENT_TIMESTAMP"]
    params = [int(player_id), *[values.get(column) for column in ATTR_COLUMNS], source]
    updates = [f"{column}=excluded.{column}" for column in ATTR_COLUMNS]
    updates += ["source=excluded.source", "updated_at=CURRENT_TIMESTAMP"]
    conn.execute(
        f"INSERT INTO pes6_player_attributes ({', '.join(columns)}) "
        f"VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT(player_id) DO UPDATE SET {', '.join(updates)}",
        params,
    )

    conn.execute(
        "DELETE FROM pes6_player_special_abilities WHERE player_id=?",
        (int(player_id),),
    )
    for ability in record.get("special_abilities") or []:
        text = str(ability).strip()
        if text:
            conn.execute(
                """
                INSERT OR IGNORE INTO pes6_player_special_abilities
                    (player_id, ability, source)
                VALUES (?, ?, ?)
                """,
                (int(player_id), text, source),
            )


def _verify_one(conn, player_id: int, record: dict) -> bool:
    row = conn.execute(
        "SELECT * FROM pes6_player_attributes WHERE player_id=? LIMIT 1",
        (int(player_id),),
    ).fetchone()
    if row is None:
        return False
    values = _values_for_record(record)
    for column in ATTR_COLUMNS:
        if column not in row.keys() or row[column] != values.get(column):
            return False

    actual_abilities = [
        str(item["ability"])
        for item in conn.execute(
            """
            SELECT ability FROM pes6_player_special_abilities
            WHERE player_id=? ORDER BY rowid
            """,
            (int(player_id),),
        ).fetchall()
    ]
    expected_abilities = [
        str(value).strip()
        for value in (record.get("special_abilities") or [])
        if str(value).strip()
    ]
    return actual_abilities == expected_abilities


def _sync_connection(runtime, conn) -> int:
    _ensure_schema(runtime, conn)
    identity, problems = build_identity_map()
    if problems:
        raise RuntimeError("SERA identity verification failed: " + " || ".join(problems[:30]))

    exact, normalized = _db_player_index(conn)
    synced = 0
    verified = 0
    missing = []

    # Use the historical AJPA roster names as identity; never use current club.
    # That makes the stat source stable even after transfers.
    for source_label, roster in _roster_sources():
        team = str(roster.get("equipo") or "").strip()
        if team not in TEAM_TO_PES_CLUB:
            continue
        for item in roster.get("jugadores") or []:
            db_name = str(item.get("nombre") or "").strip()
            key = _norm(db_name)
            record = identity.get(key)
            if not record:
                continue
            forced_team = DUPLICATE_SOURCE_TEAM.get(key)
            if forced_team and team != forced_team:
                continue

            row = _resolve_player(db_name, exact, normalized)
            if row is None:
                missing.append(f"{team}: {db_name}")
                continue

            _upsert_exact(conn, int(row["id"]), record)
            synced += 1
            if _verify_one(conn, int(row["id"]), record):
                verified += 1

    if missing or synced != EXPECTED_RECORDS or verified != EXPECTED_RECORDS:
        raise RuntimeError(
            "SERA database sync failed: "
            f"synced={synced} verified={verified} missing={len(missing)} "
            + (" | ".join(missing[:20]) if missing else "")
        )

    print(
        f"AJPA SERA STATS OFICIALES OK: synced={synced} verified={verified} "
        "source=SERA.xlsx purchases/transfers/club_history untouched"
    )
    return synced


def apply_sera_stats_authority(runtime):
    if getattr(runtime, "_ajpa_sera_stats_authority", False):
        return

    base_db = runtime.db
    synced_guilds: set[int] = set()

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

    # Apply and verify before Discord connects.
    conn = runtime.db()
    conn.close()

    runtime._ajpa_sera_stats_authority = True
    print("AJPA SERA stats authority installed: SERA.xlsx wins over legacy JSON/importers")
