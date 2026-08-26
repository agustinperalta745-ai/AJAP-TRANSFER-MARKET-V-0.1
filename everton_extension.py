"""Everton PES6 roster extension for AJAP Transfer Market.

Keeps Everton isolated from the existing multi-team file. The roster is seeded
only once on the persistent SQLite database, so later transfers and restarts do
not restore players to Everton.
"""

import multi_team_extension as multi

EVERTON = "Everton"
EVERTON_ROSTER = [
    ("Mikel Arteta", "CMF/AMF", 84),
    ("Tim Cahill", "AMF/CMF/SS", 83),
    ("Tim Howard", "GK", 82),
    ("Andrew Johnson", "CF", 82),
    ("Joseph Yobo", "CB", 82),
    ("Joleon Lescott", "CB/LB", 81),
    ("James Beattie", "CF", 80),
    ("Phil Neville", "RB/DMF", 80),
    ("James McFadden", "SS/CF", 79),
    ("Nuno Valente", "LB", 79),
    ("Lee Carsley", "DMF/CMF", 79),
    ("Andy van der Meyde", "RMF/RWF", 78),
    ("Alan Stubbs", "CB", 78),
    ("David Weir", "CB", 78),
    ("Simon Davies", "RMF/CMF", 78),
    ("Leon Osman", "AMF/CMF/RMF", 77),
    ("Tony Hibbert", "RB", 77),
    ("Gary Naysmith", "LB", 76),
    ("Richard Wright", "GK", 76),
    ("Alessandro Pistone", "LB/CB", 75),
    ("James Vaughan", "CF", 74),
    ("Victor Anichebe", "CF", 73),
    ("Iain Turner", "GK", 70),
    ("John Ruddy", "GK", 68),
]

if not any(name.casefold() == EVERTON.casefold() for name, _ in multi.ADDITIONAL_TEAMS):
    multi.ADDITIONAL_TEAMS.append((EVERTON, "Inglaterra"))

_original_seed_additional_rosters = multi.seed_additional_rosters


def seed_additional_rosters_with_everton(app):
    from lyon_test_seed import minimum_for_rating

    newly_seeded = _original_seed_additional_rosters(app)
    marker = "everton_pes6_v1"

    with app.db() as conn:
        app.add_column_if_missing(conn, "roster_players", "rating", "INTEGER")
        app.add_column_if_missing(conn, "roster_players", "min_sale_value", "INTEGER")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seed_state (
                key TEXT PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        seeded = conn.execute(
            "SELECT 1 FROM seed_state WHERE key = ?", (marker,)
        ).fetchone()
        if seeded:
            return newly_seeded

        for name, position, rating in EVERTON_ROSTER:
            conn.execute(
                """
                INSERT INTO roster_players
                    (name, position, club, added_by, rating, min_sale_value, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    position = excluded.position,
                    club = excluded.club,
                    rating = excluded.rating,
                    min_sale_value = excluded.min_sale_value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, position, EVERTON, rating, minimum_for_rating(rating)),
            )

        conn.execute("INSERT INTO seed_state (key) VALUES (?)", (marker,))

    print(f"Everton PES6 roster enabled: {len(EVERTON_ROSTER)} players.")
    return newly_seeded + len(EVERTON_ROSTER)


multi.seed_additional_rosters = seed_additional_rosters_with_everton
