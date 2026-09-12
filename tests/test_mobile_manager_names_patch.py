import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import mobile_manager_names_patch as managers


class _Member:
    def __init__(self, user_id: int, display_name: str):
        self.id = user_id
        self.display_name = display_name
        self.global_name = None
        self.name = display_name


class _Guild:
    def __init__(self, guild_id: int, members: list[_Member]):
        self.id = guild_id
        self._members = {member.id: member for member in members}

    def get_member(self, user_id: int):
        return self._members.get(user_id)

    async def fetch_member(self, user_id: int):
        member = self.get_member(user_id)
        if member is None:
            raise LookupError(user_id)
        return member


class _Bot:
    def __init__(self, guild: _Guild):
        self._guild = guild
        self.guilds = [guild]

    def get_guild(self, guild_id: int):
        return self._guild if int(guild_id) == self._guild.id else None


class MobileManagerNamesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.mobile_db = root / "mobile.db"
        self.assignment_db = root / "discord_guild.db"
        self.old_env = {
            key: os.environ.get(key)
            for key in ("DB_PATH", "AJAP_LEGACY_GUILD_ID", "AJPA_MOBILE_GUILD_ID", "DISCORD_GUILD_ID")
        }
        os.environ["DB_PATH"] = str(self.mobile_db)
        os.environ["AJAP_LEGACY_GUILD_ID"] = "777"
        os.environ["AJPA_MOBILE_GUILD_ID"] = "777"
        os.environ.pop("DISCORD_GUILD_ID", None)

        with sqlite3.connect(self.assignment_db) as conn:
            conn.execute("CREATE TABLE clubs (user_id INTEGER, name TEXT)")
            conn.executemany(
                "INSERT INTO clubs(user_id,name) VALUES(?,?)",
                [(10, "Marsella"), (20, "PSG"), (30, "Ajax")],
            )

        # The Mobile DB intentionally has no clubs table. This reproduces the
        # production bug: standings and Discord assignments live in different DBs.
        with sqlite3.connect(self.mobile_db):
            pass

        def db_for_guild(guild_id: int):
            self.assertEqual(int(guild_id), 777)
            conn = sqlite3.connect(self.assignment_db)
            conn.row_factory = sqlite3.Row
            return conn

        self.runtime = SimpleNamespace(db_for_guild=db_for_guild)
        self.guild = _Guild(
            777,
            [
                _Member(10, "Agustin | Marsella"),
                _Member(20, "Tomi | PSG"),
                _Member(30, "Santi | Ajax"),
            ],
        )
        self.bot = _Bot(self.guild)

    async def asyncTearDown(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()

    async def test_refresh_reads_real_guild_db_and_writes_mobile_cache(self):
        await managers._refresh_manager_names(self.runtime, self.bot)

        conn = sqlite3.connect(self.mobile_db)
        conn.row_factory = sqlite3.Row
        try:
            manager_map = managers._manager_map(conn)
        finally:
            conn.close()

        self.assertEqual(
            manager_map[managers._club_key("Olympique de Marsella")]["manager_name"],
            "Agustin",
        )
        self.assertEqual(
            manager_map[managers._club_key("Paris Saint-Germain")]["manager_name"],
            "Tomi",
        )
        self.assertEqual(manager_map[managers._club_key("Ajax")]["manager_name"], "Santi")

    def test_known_ges_aliases_share_the_same_key(self):
        self.assertEqual(managers._club_key("PSG"), managers._club_key("Paris Saint-Germain"))
        self.assertEqual(managers._club_key("Marsella"), managers._club_key("Olympique de Marsella"))
        self.assertEqual(managers._club_key("Lyon"), managers._club_key("Olympique de Lyon"))
        self.assertEqual(managers._club_key("Monaco"), managers._club_key("AS Monaco"))


if __name__ == "__main__":
    unittest.main()
