import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import classic_rival_dm_patch as dm
import classic_rival_discord_patch as ui
import mobile_classic_rival_api_patch as classic


class ClassicDMTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'guild.db'
        with self.connect() as conn:
            classic.ensure_schema(conn)
            conn.execute("INSERT INTO classic_rival_requests (requester_club,target_club,requester_user_id,target_user_id) VALUES ('Ajax','Everton',1,2)")
        self.interaction = SimpleNamespace(
            user=SimpleNamespace(id=2), guild=None,
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
            edit_original_response=AsyncMock(),
        )

    def tearDown(self):
        self.temp.cleanup()

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def guild_db(self, guild_id):
        self.assertEqual(guild_id, 42)
        return self.connect()

    async def click(self, action):
        with patch.object(ui, 'APP', SimpleNamespace(db_for_guild=self.guild_db)), patch.object(classic.mobile_write_api, '_require_club', return_value='Everton'), patch.object(ui, '_dm', AsyncMock()):
            await dm.ClassicDMAction(42, 1, action).callback(self.interaction)

    async def test_dm_accept_and_repeat(self):
        await self.click('ACCEPT')
        self.interaction.edit_original_response.assert_awaited_once()
        self.assertIsNone(self.interaction.edit_original_response.call_args.kwargs['view'])
        await self.click('ACCEPT')
        self.interaction.followup.send.assert_awaited_once()
        with self.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM classic_rivals').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM classic_market_outbox').fetchone()[0], 1)

    async def test_dm_reject(self):
        await self.click('REJECT')
        with self.connect() as conn:
            self.assertEqual(conn.execute('SELECT status FROM classic_rival_requests').fetchone()[0], 'REJECTED')
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM classic_market_outbox').fetchone()[0], 0)

    async def test_wrong_user_cannot_respond(self):
        self.interaction.user.id = 999
        await self.click('ACCEPT')
        self.interaction.edit_original_response.assert_not_awaited()
        self.interaction.followup.send.assert_awaited_once()
        with self.connect() as conn:
            self.assertEqual(conn.execute('SELECT status FROM classic_rival_requests').fetchone()[0], 'PENDING')

    async def test_app_response_makes_old_dm_button_stale(self):
        with self.connect() as conn, patch.object(classic.mobile_write_api, '_require_club', return_value='Everton'):
            classic._respond_classic(conn, {'user_id': 2}, {'request_id': 1, 'decision': 'ACCEPT'})
        await self.click('REJECT')
        self.interaction.edit_original_response.assert_not_awaited()
        with self.connect() as conn:
            self.assertEqual(conn.execute('SELECT status FROM classic_rival_requests').fetchone()[0], 'ACCEPTED')

    async def test_mobile_components_rehydrate_after_restart(self):
        components = dm.request_components(42, 1)
        view = dm.request_view(42, 1)
        self.assertTrue(view.is_persistent())
        self.assertEqual(components, view.to_components())
        for spec in components[0]['components']:
            match = re.fullmatch(dm.ClassicDMAction.__discord_ui_compiled_template__, spec['custom_id'])
            button = await dm.ClassicDMAction.from_custom_id(None, None, match)
            self.assertEqual(button.guild_id, 42)
            self.assertEqual(button.request_id, 1)

    async def test_mobile_dm_includes_buttons(self):
        components = dm.request_components(42, 1)
        with patch.object(classic, '_discord_json', side_effect=[{'id': '123'}, {'id': '456'}]) as api:
            classic._send_dm(2, 'Nueva propuesta', components=components)
        self.assertEqual(api.call_args.args, ('/channels/123/messages', 'POST', {'content': 'Nueva propuesta', 'components': components}))

    async def test_schema_preserves_response_transaction(self):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            classic.ensure_schema(conn)
            self.assertTrue(conn.in_transaction)
            conn.rollback()
