"""One-time per-guild sync for teams added after guild isolation was introduced.

Guild databases that already existed before Newcastle/Everton were added do not
receive later base-database seeds automatically. This patch adds only missing
players for those new clubs and refreshes OVR/position without ever overwriting
a player's current club, so completed transfers remain untouched.
"""

from __future__ import annotations

import guild_isolation_patch as guild_isolation
from everton_extension import EVERTON, EVERTON_ROSTER
from newcastle_extension import NEWCASTLE, NEWCASTLE_ROSTER


NEW_TEAM_ROSTERS = [
    (NEWCASTLE, "Inglaterra", NEWCASTLE_ROSTER, "newcastle_united_pes6_v1"),
    (EVERTON, "Inglaterra", EVERTON_ROSTER, "everton_pes6_v1"),
]


def _sync_connection(runtime, conn):
    from lyon_test_seed import minimum_for_rating

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

    for club, country, roster, marker in NEW_TEAM_ROSTERS:
        seeded = conn.execute(
            "SELECT 1 FROM seed_state WHERE key = ?",
            (marker,),
        ).fetchone()
        if seeded:
            continue

        conn.execute(
            """
            INSERT INTO league_teams (name, country, active)
            VALUES (?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET
                country = excluded.country,
                active = 1
            """,
            (club, country),
        )

        for name, position, rating in roster:
            # Never restore excluded.club on conflict. If a player has already
            # moved, keep the current club and refresh only static metadata.
            conn.execute(
                """
                INSERT INTO roster_players
                    (name, position, club, added_by, rating, min_sale_value, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    position = excluded.position,
                    rating = excluded.rating,
                    min_sale_value = excluded.min_sale_value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    name,
                    position,
                    club,
                    rating,
                    minimum_for_rating(rating),
                ),
            )

        conn.execute("INSERT OR IGNORE INTO seed_state (key) VALUES (?)", (marker,))


def apply_additional_roster_sync(runtime):
    if getattr(runtime, "_ajap_additional_roster_sync", False):
        return

    base_db = runtime.db
    synced_guilds = set()

    def synced_db():
        conn = base_db()
        guild_id = int(runtime.current_guild_id())
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

    runtime.db = synced_db
    runtime._ajap_additional_roster_sync = True
    print("AJAP guild roster sync activo: Newcastle + Everton sin resetear transferencias")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_sync(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_additional_roster_sync(runtime)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_additional_roster_sync_wrapped",
    False,
):
    _apply_guild_isolation_then_sync._ajap_additional_roster_sync_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_sync


# Tottenham already existed in the old fixed seed. Import its JSON replacement
# here so the migration is part of the same pre-run per-guild roster sync chain.
import tottenham_hotspur_roster_replace_patch  # noqa: E402,F401
