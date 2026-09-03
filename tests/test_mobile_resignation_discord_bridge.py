import sqlite3

import mobile_resignation_api_patch
import mobile_write_api


def test_mobile_resignation_queues_discord_vacancy(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE clubs (user_id INTEGER, name TEXT)")
    conn.execute("INSERT INTO clubs(user_id, name) VALUES(?, ?)", (42, "Ajax"))

    monkeypatch.setattr(
        mobile_write_api,
        "_require_club",
        lambda _conn, _session: "Ajax",
    )

    result = mobile_resignation_api_patch._resign(conn, {"user_id": 42})

    assert result["ok"] is True
    assert result["club"] == "Ajax"
    assert conn.execute(
        "SELECT COUNT(*) FROM clubs WHERE user_id=42"
    ).fetchone()[0] == 0

    history = conn.execute(
        """
        SELECT user_id, club, action, actor_id
        FROM club_assignment_history
        """
    ).fetchone()
    assert tuple(history) == (42, "Ajax", "RENUNCIA_DT", 42)

    queued = conn.execute(
        """
        SELECT user_id, club, status, attempts
        FROM mobile_resignation_discord_outbox
        """
    ).fetchone()
    assert tuple(queued) == (42, "Ajax", "PENDING", 0)

    conn.close()
