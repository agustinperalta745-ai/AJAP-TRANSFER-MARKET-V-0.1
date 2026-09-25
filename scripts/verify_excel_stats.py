from __future__ import annotations

import sqlite3

import excel_stats_authority_patch as patch


DUPLICATE_SURVIVORS = {
    "Cahill": "Everton",
    "Leo": "Benfica",
    "Gardner": "Bolton Wanderers",
    "Walker": "West Ham United",
    "Adriano": "Sevilla FC",
}


class FakeRuntime:
    @staticmethod
    def add_column_if_missing(conn, table, name, type_name):
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if name not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {type_name}")


def make_db(records):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE roster_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            club TEXT NOT NULL,
            position TEXT,
            rating INTEGER,
            min_sale_value INTEGER
        )
        """
    )
    conn.execute("CREATE TABLE transfers (id INTEGER PRIMARY KEY, marker TEXT)")
    conn.execute("CREATE TABLE offers (id INTEGER PRIMARY KEY, marker TEXT)")
    conn.execute("CREATE TABLE club_balances (club TEXT PRIMARY KEY, balance INTEGER)")
    conn.execute("INSERT INTO transfers VALUES (1, 'KEEP_TRANSFER')")
    conn.execute("INSERT INTO offers VALUES (1, 'KEEP_OFFER')")
    conn.execute("INSERT INTO club_balances VALUES ('KEEP_CLUB', 123456789)")

    inserted = {}
    for record in records:
        name = str(record["name"])
        if name in inserted:
            continue
        club = DUPLICATE_SURVIVORS.get(name, str(record["team"]))
        conn.execute(
            "INSERT INTO roster_players (name, club, position, rating, min_sale_value) VALUES (?, ?, ?, ?, ?)",
            (name, club, "TEST", 77, 123000000),
        )
        inserted[name] = club
    conn.commit()
    return conn


records = patch._load_payload()
assert len(records) == 623, len(records)
assert len({str(record["name"]).casefold() for record in records}) == 617

conn = make_db(records)
before = {
    "transfers": [tuple(row) for row in conn.execute("SELECT * FROM transfers").fetchall()],
    "offers": [tuple(row) for row in conn.execute("SELECT * FROM offers").fetchall()],
    "balances": [tuple(row) for row in conn.execute("SELECT * FROM club_balances").fetchall()],
    "roster": [
        tuple(row)
        for row in conn.execute(
            "SELECT id,name,club,position,rating,min_sale_value FROM roster_players ORDER BY id"
        ).fetchall()
    ],
}

synced = patch._sync_connection(FakeRuntime(), conn)
assert synced == 617, synced

after = {
    "transfers": [tuple(row) for row in conn.execute("SELECT * FROM transfers").fetchall()],
    "offers": [tuple(row) for row in conn.execute("SELECT * FROM offers").fetchall()],
    "balances": [tuple(row) for row in conn.execute("SELECT * FROM club_balances").fetchall()],
    "roster": [
        tuple(row)
        for row in conn.execute(
            "SELECT id,name,club,position,rating,min_sale_value FROM roster_players ORDER BY id"
        ).fetchall()
    ],
}
assert before == after, "SERA sync touched non-stat production data"

count = conn.execute("SELECT COUNT(*) AS n FROM pes6_player_attributes").fetchone()["n"]
assert count == 617, count

def stats(name):
    return conn.execute(
        """
        SELECT a.*
        FROM pes6_player_attributes a
        JOIN roster_players p ON p.id=a.player_id
        WHERE p.name=? COLLATE NOCASE
        """,
        (name,),
    ).fetchone()

riquelme = stats("Juan Román Riquelme")
assert riquelme["attack"] == 83
assert riquelme["defence"] == 52
assert riquelme["short_pass_accuracy"] == 98
assert riquelme["technique"] == 93
assert riquelme["injury_resistance"] == "A"

huntelaar = stats("Huntelaar")
assert huntelaar["attack"] == 85

assert stats("Cahill")["attack"] == 78
assert stats("Leo") is not None
assert stats("Gardner") is not None
assert stats("Walker")["attack"] == 30
assert stats("Adriano")["attack"] == 77

sources = conn.execute(
    "SELECT COUNT(DISTINCT source) AS n, MIN(source) AS source FROM pes6_player_attributes"
).fetchone()
assert sources["n"] == 1
assert sources["source"] == patch.SOURCE_LABEL

print("SERA payload OK: 623 source rows -> 617 AJPA player identities")
print("DB sync OK: 617/617 verified")
print("Protected data OK: transfers/offers/clubs/OVR/value untouched")
print(
    "Riquelme OK:",
    riquelme["attack"],
    riquelme["defence"],
    riquelme["short_pass_accuracy"],
    riquelme["technique"],
    riquelme["injury_resistance"],
)
