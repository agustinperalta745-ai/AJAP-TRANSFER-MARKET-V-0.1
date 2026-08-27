"""Safe Aston Villa JSON migration plus Tottenham duplicate-name startup guard.

This module fixes two migration hazards in the persistent AJAP database:
1) Tottenham's legacy full-name -> short-name migration can find both versions
   already present and hit roster_players.name UNIQUE while renaming.
2) Aston Villa's JSON contains "Cahill", which must not overwrite Everton's
   Tim Cahill. Aston Villa uses the unambiguous database name "Gary Cahill".
"""

from __future__ import annotations

import aston_villa_roster_patch as villa_v1
import everton_extension as everton
import tottenham_hotspur_roster_replace_patch as spurs


ASTON_VILLA = villa_v1.ASTON_VILLA
COUNTRY = villa_v1.COUNTRY
MIGRATION_MARKER = "aston_villa_json_v2_unique_names_20260827"

# The uploaded PES6 JSON remains untouched. Only the database/display name is
# disambiguated where the global roster name UNIQUE constraint requires it.
DB_NAME_BY_SOURCE = {
    "Cahill": "Gary Cahill",
}
SOURCE_NAME_BY_DB = {
    DB_NAME_BY_SOURCE.get(source_name, source_name): source_name
    for source_name in villa_v1.POSITION_BY_PLAYER
}

ASTON_VILLA_ROSTER = [
    (
        DB_NAME_BY_SOURCE.get(source_name, source_name),
        position,
        villa_v1._rating(position, villa_v1.ASTON_VILLA_DATA[source_name]["stats"]),
    )
    for source_name, position in villa_v1.POSITION_BY_PLAYER.items()
]


def _install_tottenham_unique_guard():
    """Prefer an existing canonical Spurs row before trying a legacy rename.

    Old databases can contain both e.g. "Dimitar Berbatov" and "Berbatov".
    The old migration chose the legacy row first and then tried to rename it to
    an already-existing canonical row, causing SQLite UNIQUE to abort startup.
    """

    if getattr(spurs, "_ajap_unique_name_guard_v2", False):
        return

    def _find_player_canonical_first(conn, canonical):
        canonical_row = conn.execute(
            "SELECT * FROM roster_players WHERE name = ? COLLATE NOCASE LIMIT 1",
            (canonical,),
        ).fetchone()
        if canonical_row:
            return canonical_row, canonical

        for candidate in spurs.OLD_NAMES.get(canonical, ()):
            row = conn.execute(
                "SELECT * FROM roster_players WHERE name = ? COLLATE NOCASE LIMIT 1",
                (candidate,),
            ).fetchone()
            if row:
                return row, candidate
        return None, None

    spurs._find_player = _find_player_canonical_first
    spurs._ajap_unique_name_guard_v2 = True
    print("AJAP Tottenham guard activo: nombres canónicos tienen prioridad sobre aliases")


_install_tottenham_unique_guard()


def _canonical_players_present(conn):
    names = [name for name, _position, _rating in ASTON_VILLA_ROSTER]
    marks = ",".join("?" for _ in names)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM roster_players WHERE name COLLATE NOCASE IN ({marks})",
        tuple(names),
    ).fetchone()
    return int(row["n"] if row else 0)


def _restore_everton_cahill(runtime, conn):
    """Repair Tim Cahill if the v1 Villa migration ever touched his shared name."""
    from lyon_test_seed import minimum_for_rating

    row = conn.execute(
        "SELECT id FROM roster_players WHERE name = ? COLLATE NOCASE LIMIT 1",
        ("Cahill",),
    ).fetchone()
    if not row:
        return

    source_name = "Cahill"
    position = everton.POSITION_BY_PLAYER[source_name]
    payload = everton.EVERTON_DATA[source_name]
    rating = everton._rating(position, payload["stats"])
    player_id = int(row["id"])

    conn.execute(
        "UPDATE roster_players SET position = ?, rating = ?, min_sale_value = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (position, rating, minimum_for_rating(rating), player_id),
    )
    everton._upsert_attributes(conn, player_id, payload)


def _sync_connection(runtime, conn):
    from lyon_test_seed import minimum_for_rating

    villa_v1._ensure_schema(runtime, conn)

    # Always repair the shared Everton name first. This is idempotent and keeps
    # the player's current club intact if Tim Cahill has already transferred.
    _restore_everton_cahill(runtime, conn)

    if _canonical_players_present(conn) < len(ASTON_VILLA_ROSTER):
        conn.execute("DELETE FROM seed_state WHERE key = ?", (MIGRATION_MARKER,))

    done = conn.execute(
        "SELECT 1 FROM seed_state WHERE key = ?",
        (MIGRATION_MARKER,),
    ).fetchone()
    if done:
        conn.execute(
            "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
            "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
            (ASTON_VILLA, COUNTRY),
        )
        return 0

    changed = 0
    for db_name, position, rating in ASTON_VILLA_ROSTER:
        source_name = SOURCE_NAME_BY_DB[db_name]
        payload = villa_v1.ASTON_VILLA_DATA[source_name]
        row = conn.execute(
            "SELECT id, club FROM roster_players WHERE name = ? COLLATE NOCASE LIMIT 1",
            (db_name,),
        ).fetchone()

        if row:
            player_id = int(row["id"])
            # Static data is safe to refresh. Never reset club: completed
            # transfers must remain exactly where they are.
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
                (db_name, position, ASTON_VILLA, rating, minimum_for_rating(rating)),
            )
            player_id = int(cursor.lastrowid)

        villa_v1._upsert_attributes(conn, player_id, payload)
        changed += 1

    conn.execute(
        "INSERT INTO league_teams (name, country, active) VALUES (?, ?, 1) "
        "ON CONFLICT(name) DO UPDATE SET country = excluded.country, active = 1",
        (ASTON_VILLA, COUNTRY),
    )
    if "deleted_teams" in villa_v1._tables(conn):
        conn.execute(
            "DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE",
            (ASTON_VILLA,),
        )

    conn.execute(
        "INSERT OR IGNORE INTO seed_state (key) VALUES (?)",
        (MIGRATION_MARKER,),
    )
    return changed


def apply_aston_villa_json(runtime):
    if getattr(runtime, "_ajap_aston_villa_json_v2", False):
        return

    base_db = runtime.db
    synced_guilds = set()

    def aston_villa_synced_db():
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
                    f"AJAP Aston Villa v2 cargado: guild={guild_id} • "
                    f"{len(ASTON_VILLA_ROSTER)} jugadores • Gary Cahill protegido"
                )
        except Exception:
            conn.close()
            raise
        return conn

    runtime.db = aston_villa_synced_db
    runtime._ajap_aston_villa_json_v2 = True
    print(
        f"AJAP migración Aston Villa v2 activa: {len(ASTON_VILLA_ROSTER)} jugadores • "
        "nombres globales protegidos"
    )


OVR_BY_PLAYER = {name: rating for name, _position, rating in ASTON_VILLA_ROSTER}
print(f"AJAP Aston Villa v2 listo: {len(ASTON_VILLA_ROSTER)} jugadores")
