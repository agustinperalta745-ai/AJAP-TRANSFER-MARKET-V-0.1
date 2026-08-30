"""Compatibility guard for older AJPA finance schemas used by mobile releases."""

from __future__ import annotations

import mobile_write_api


def apply() -> None:
    if getattr(mobile_write_api, "_ajpa_release_finance_compat", False):
        return

    original = mobile_write_api.release_player

    def compatible_release(conn, session, player_id):
        # Some persistent guild databases were created before club_finances gained
        # updated_at. The release flow updates that timestamp, so add a nullable
        # compatibility column only when an old DB is missing it.
        if mobile_write_api._table_exists(conn, "club_finances"):
            columns = mobile_write_api._columns(conn, "club_finances")
            if "updated_at" not in columns:
                conn.execute("ALTER TABLE club_finances ADD COLUMN updated_at DATETIME")
        return original(conn, session, player_id)

    mobile_write_api.release_player = compatible_release
    mobile_write_api._ajpa_release_finance_compat = True
