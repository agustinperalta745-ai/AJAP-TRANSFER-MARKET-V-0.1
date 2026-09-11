import sqlite3

import club_access_revocation as access


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE clubs (
            name TEXT PRIMARY KEY COLLATE NOCASE,
            user_id INTEGER
        );
        CREATE TABLE mobile_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            is_staff INTEGER NOT NULL DEFAULT 0,
            expires_at INTEGER NOT NULL,
            revoked_at INTEGER,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE mobile_pair_codes (
            code TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            is_staff INTEGER NOT NULL DEFAULT 0,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            created_at INTEGER NOT NULL
        );
        """
    )
    return conn


def _seed_credentials(conn: sqlite3.Connection, user_id: int, *, is_staff: bool) -> None:
    staff = 1 if is_staff else 0
    conn.execute("INSERT INTO clubs(name, user_id) VALUES('Ajax', ?)", (user_id,))
    conn.execute(
        "INSERT INTO mobile_sessions(token_hash,user_id,is_staff,expires_at,created_at) VALUES(?,?,?,?,?)",
        (f"session-{user_id}-{staff}", user_id, staff, 9999999999, 1),
    )
    conn.execute(
        "INSERT INTO mobile_pair_codes(code,user_id,is_staff,expires_at,created_at) VALUES(?,?,?,?,?)",
        (f"CODE{user_id:04d}"[-8:], user_id, staff, 9999999999, 1),
    )


def test_admin_keeps_mobile_access_when_only_club_is_unassigned():
    conn = _conn()
    _seed_credentials(conn, 10, is_staff=True)

    result = access.unassign_user_in_conn(
        conn,
        10,
        actor_id=99,
        source="ADMIN_MOBILE",
    )

    assert result["club"] == "Ajax"
    assert result["sessions_revoked"] == 0
    assert result["pair_codes_revoked"] == 0
    assert result["staff_access_preserved"] is True
    assert conn.execute("SELECT 1 FROM clubs WHERE user_id=10").fetchone() is None
    assert conn.execute("SELECT revoked_at FROM mobile_sessions WHERE user_id=10").fetchone()[0] is None
    assert conn.execute("SELECT used_at FROM mobile_pair_codes WHERE user_id=10").fetchone()[0] is None


def test_normal_manager_loses_mobile_access_when_club_is_unassigned():
    conn = _conn()
    _seed_credentials(conn, 20, is_staff=False)

    result = access.unassign_user_in_conn(
        conn,
        20,
        actor_id=99,
        source="ADMIN_MOBILE",
    )

    assert result["sessions_revoked"] == 1
    assert result["pair_codes_revoked"] == 1
    assert result["staff_access_preserved"] is False
    assert conn.execute("SELECT revoked_at FROM mobile_sessions WHERE user_id=20").fetchone()[0] is not None
    assert conn.execute("SELECT used_at FROM mobile_pair_codes WHERE user_id=20").fetchone()[0] is not None


def test_discord_departure_revokes_staff_access_too():
    conn = _conn()
    _seed_credentials(conn, 30, is_staff=True)

    result = access.unassign_user_in_conn(
        conn,
        30,
        source="DISCORD_LEFT_EVENT",
    )

    assert result["sessions_revoked"] == 1
    assert result["pair_codes_revoked"] == 1
    assert result["staff_access_preserved"] is False
    assert conn.execute("SELECT revoked_at FROM mobile_sessions WHERE user_id=30").fetchone()[0] is not None
    assert conn.execute("SELECT used_at FROM mobile_pair_codes WHERE user_id=30").fetchone()[0] is not None
