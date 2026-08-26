"""Newcastle United PES6 roster extension for AJAP Transfer Market.

Keeps Newcastle isolated from the existing multi-team file. The roster is
seeded only once on the persistent SQLite database, so later transfers and
restarts do not restore players to Newcastle.
"""

import multi_team_extension as multi

NEWCASTLE = "Newcastle United"
NEWCASTLE_ROSTER = [
    ("Michael Owen", "CF", 88),
    ("Shay Given", "GK", 86),
    ("Damien Duff", "LWF/LMF", 86),
    ("Obafemi Martins", "CF", 85),
    ("Nolberto Solano", "RMF/RWF", 84),
    ("Emre Belözoğlu", "CMF/AMF", 84),
    ("Scott Parker", "CMF/DMF", 84),
    ("Kieron Dyer", "CMF/RMF", 82),
    ("Albert Luque", "CF/LWF", 82),
    ("Nicky Butt", "DMF/CMF", 81),
    ("James Milner", "RMF/RWF", 80),
    ("Stephen Carr", "RB", 79),
    ("Charles N'Zogbia", "LMF/LWF", 79),
    ("Shola Ameobi", "CF", 79),
    ("Steve Harper", "GK", 78),
    ("Craig Moore", "CB", 78),
    ("Giuseppe Rossi", "CF/SS", 78),
    ("Antoine Sibierski", "AMF/CF", 78),
    ("Celestine Babayaro", "LB", 77),
    ("Steven Taylor", "CB", 77),
    ("Titus Bramble", "CB", 76),
    ("Peter Ramage", "CB/RB", 74),
]

# Add Newcastle to the existing selector before Bot.run() installs team assignment.
if not any(name.casefold() == NEWCASTLE.casefold() for name, _ in multi.ADDITIONAL_TEAMS):
    multi.ADDITIONAL_TEAMS.append((NEWCASTLE, "Inglaterra"))

_original_seed_additional_rosters = multi.seed_additional_rosters


def seed_additional_rosters_with_newcastle(app):
    """Run all existing seeds, then seed Newcastle exactly once."""
    from lyon_test_seed import minimum_for_rating

    newly_seeded = _original_seed_additional_rosters(app)
    marker = "newcastle_united_pes6_v1"

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

        for name, position, rating in NEWCASTLE_ROSTER:
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
                (
                    name,
                    position,
                    NEWCASTLE,
                    rating,
                    minimum_for_rating(rating),
                ),
            )

        conn.execute("INSERT INTO seed_state (key) VALUES (?)", (marker,))

    print(
        f"Newcastle United PES6 roster enabled: {len(NEWCASTLE_ROSTER)} players."
    )
    return newly_seeded + len(NEWCASTLE_ROSTER)


# sitecustomize imports this function later by name from multi_team_extension.
multi.seed_additional_rosters = seed_additional_rosters_with_newcastle
