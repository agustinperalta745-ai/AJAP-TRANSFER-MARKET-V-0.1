"""Load Olympique de Lyon from data/Lyon.json with full PES6 stats and AJAP OVR.

This replaces the old Lyon test seed names with the canonical JSON names while
preserving the existing roster_player row (and therefore its current club) when
the same player already exists under the legacy full name.
"""

from __future__ import annotations

import json
from pathlib import Path

import fiorentina_roster_patch as roster_base
import guild_isolation_patch as guild_isolation
import team_assignment as teams

LYON = "Olympique de Lyon"
COUNTRY = "Francia"
MIGRATION_MARKER = "lyon_json_v1_ovr3_20260827"
SOURCE = "Lyon.json • OVR AJPA promedio de 3 stats • 2026-08-27"
SOURCE_PATH = Path(__file__).resolve().parent / "data" / "Lyon.json"

POSITION_BY_PLAYER = {
    "Govou": "RMF/SS",
    "Fred": "CF",
    "Benzema": "CF/SS",
    "Wiltord": "CF/SS",
    "Carew": "CF",
    "Bettiol": "CF",
    "Alou Diarra": "DMF",
    "Toulalan": "DMF/CMF",
    "Juninho": "AMF/CMF",
    "Malouda": "LMF/WF",
    "Tiago": "CMF",
    "Ben Arfa": "AMF/SMF",
    "Kallstrom": "CMF/DMF",
    "Hima": "DMF",
    "Idangar": "WF/LMF",
    "Cris": "CB",
    "Cacapa": "CB",
    "Clerc": "RB",
    "Abidal": "LB/CB",
    "Squillaci": "CB",
    "Muller": "CB",
    "Reveillere": "RB",
    "Berthod": "LB",
    "Benhamida": "RB",
    "Coupet": "GK",
    "Vercoutre": "GK",
    "Hartock": "GK",
}

LEGACY_ALIASES = {
    "Govou": ("Sidney Govou",),
    "Benzema": ("Karim Benzema",),
    "Wiltord": ("Sylvain Wiltord",),
    "Carew": ("John Carew",),
    "Bettiol": ("Grégory Bettiol",),
    "Toulalan": ("Jérémy Toulalan",),
    "Juninho": ("Juninho Pernambucano",),
    "Malouda": ("Florent Malouda",),
    "Tiago": ("Tiago Mendes",),
    "Ben Arfa": ("Hatem Ben Arfa",),
    "Kallstrom": ("Kim Källström",),
    "Hima": ("Yacine Hima",),
    "Idangar": ("Sylvain Idangar",),
    "Cacapa": ("Cláudio Caçapa",),
    "Clerc": ("François Clerc",),
    "Abidal": ("Éric Abidal",),
    "Squillaci": ("Sébastien Squillaci",),
    "Muller": ("Patrick Müller",),
    "Reveillere": ("Anthony Réveillère",),
    "Berthod": ("Jérémy Berthod",),
    "Benhamida": ("Mourad Benhamida",),
    "Coupet": ("Grégory Coupet",),
    "Vercoutre": ("Rémy Vercoutre",),
    "Hartock": ("Joan Hartock",),
}

# Present only in the historical test roster. Remove them from Lyon only if they
# never left the club, so a real transfer done during testing is not destroyed.
LEGACY_TEST_ONLY = ("Romain Beynié", "Loïc Rémy")

STAT_MAP = roster_base.STAT_MAP
ATTR_COLUMNS = roster_base.ATTR_COLUMNS


def _load_source():
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if str(payload.get("equipo", "")).strip().casefold() != LYON.casefold():
        raise ValueError("Lyon.json no corresponde a Olympique de Lyon")
    players = payload.get("jugadores") or []
    by_name = {str(player["nombre"]).strip(): player for player in players}
    if len(players) != 27 or set(by_name) != set(POSITION_BY_PLAYER):
        missing = sorted(set(POSITION_BY_PLAYER) - set(by_name))
        extra = sorted(set(by_name) - set(POSITION_BY_PLAYER))
        raise ValueError(
            f"Lyon.json inválido: jugadores={len(players)} "
            f"faltan={missing or '-'} sobran={extra or '-'}"
        )
    return by_name


LYON_DATA = _load_source()


def _rating(position, stats):
    return roster_base._rating(position, stats)


LYON_ROSTER = [
    (name, POSITION_BY_PLAYER[name], _rating(POSITION_BY_PLAYER[name], LYON_DATA[name]["stats"]))
    for name in POSITION_BY_PLAYER
]

if not any(name.casefold() == LYON.casefold() for name, _country in teams.OFFICIAL_TEAMS):
    teams.OFFICIAL_TEAMS.append((LYON, COUNTRY))
teams.OFFICIAL[LYON.casefold()] = LYON


def _delete_roster_row(conn, player_id):
    tables = roster_base._tables(conn)
    if "pes6_player_special_abilities" in tables:
        conn.execute(
            "DELETE FROM pes6_player_special_abilities WHERE player_id = ?",
            (player_id,),
        )
    if "pes6_player_attributes" in tables:
        conn.execute("DELETE FROM pes6_player_attributes WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM roster_players WHERE id = ?", (player_id,))


def _migrate_legacy_names(conn):
    """Collapse old full-name Lyon seed rows into canonical JSON identities."""
    for canonical, aliases in LEGACY_ALIASES.items():
        canonical_row = conn.execute(
            "SELECT id, club FROM roster_players WHERE name = ? COLLATE NOCASE LIMIT 1",
            (canonical,),
        ).fetchone()

        alias_rows = []
        for alias in aliases:
            row = conn.execute(
                "SELECT id, name, club FROM roster_players "
                "WHERE name = ? COLLATE NOCASE LIMIT 1",
                (alias,),
            ).fetchone()
            if row:
                alias_rows.append(row)

        if not alias_rows:
            continue

        if canonical_row is None:
            keeper = alias_rows.pop(0)
            conn.execute(
                "UPDATE roster_players SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (canonical, int(keeper["id"])),
            )
            canonical_row = {"id": int(keeper["id"]), "club": keeper["club"]}

        for alias_row in alias_rows:
            alias_id = int(alias_row["id"])
            alias_club = str(alias_row["club"] or "")
            canonical_club = str(canonical_row["club"] or "")

            # If a legacy row was already transferred, preserve that id/current
            # club instead of a duplicate canonical row that still sits at Lyon.
            if (
                alias_club.casefold() != LYON.casefold()
                and canonical_club.casefold() == LYON.casefold()
            ):
                canonical_id = int(canonical_row["id"])
                _delete_roster_row(conn, canonical_id)
                conn.execute(
                    "UPDATE roster_players SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (canonical, alias_id),
                )
                canonical_row = {"id": alias_id, "club": alias_row["club"]}
            elif alias_club.casefold() == LYON.casefold():
                _delete_roster_row(conn, alias_id)


def _remove_test_only_players_still_at_lyon(conn):
    for legacy_name in LEGACY_TEST_ONLY:
        row = conn.execute(
            "SELECT id FROM roster_players "
            "WHERE name = ? COLLATE NOCASE AND club = ? COLLATE NOCASE LIMIT 1",
            (legacy_name, LYON),
        ).fetchone()
        if row:
            _delete_roster_row(conn, int(row["id"]))


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
    _migrate_legacy_names(conn)
    _remove_test_only_players_still_at_lyon(conn)

    names = [name for name, _position, _rating_value in LYON_ROSTER]
    marks = ",".join("?" for _ in names)
    present = conn.execute(
        f"SELECT COUNT(*) AS n FROM roster_players WHERE name COLLATE NOCASE IN ({marks})",
        tuple(names),
    ).fetchone()
    if int(present["n"] if present else 0) < len(LYON_ROSTER):
        conn.execute("DELETE FROM seed_state WHERE key = ?", (MIGRATION_MARKER,))

    done = conn.execute("SELECT 1 FROM seed_state WHERE key = ?", (MIGRATION_MARKER,)).fetchone()
    if done:
        conn.execute(
            "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
            "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
            (LYON, COUNTRY),
        )
        return 0

    changed = 0
    for name, position, rating in LYON_ROSTER:
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
                (name, position, LYON, rating, minimum_for_rating(rating)),
            )
            player_id = int(cursor.lastrowid)
        _upsert_attributes(conn, player_id, LYON_DATA[name])
        changed += 1

    conn.execute(
        "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
        "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
        (LYON, COUNTRY),
    )
    if "deleted_teams" in roster_base._tables(conn):
        conn.execute("DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE", (LYON,))
    conn.execute("INSERT OR IGNORE INTO seed_state (key) VALUES (?)", (MIGRATION_MARKER,))
    return changed


def apply_lyon_json(runtime):
    if getattr(runtime, "_ajap_lyon_json", False):
        return
    base_db = runtime.db
    synced_guilds = set()

    def lyon_synced_db():
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
                    f"AJAP Lyon cargado: guild={guild_id} • "
                    f"{len(LYON_ROSTER)} jugadores desde Lyon.json"
                )
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = lyon_synced_db
    runtime._ajap_lyon_json = True
    print(
        f"AJAP migración Lyon activa: {len(LYON_ROSTER)} jugadores • "
        "OVR AJPA de 3 stats"
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_lyon(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_lyon_json(runtime)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_lyon_json_wrapped",
    False,
):
    _apply_guild_isolation_then_lyon._ajap_lyon_json_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_lyon


OVR_BY_PLAYER = {name: rating for name, _position, rating in LYON_ROSTER}
print(f"AJAP Lyon JSON listo: {len(LYON_ROSTER)} jugadores")
