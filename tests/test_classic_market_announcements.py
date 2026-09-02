import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import mobile_classic_rival_api_patch as classic
import classic_market_announcement_patch as feed


class ClassicAnnouncementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'league.db'
        self.conn = self.connect()
        classic.ensure_schema(self.conn)
        self.conn.execute("INSERT INTO classic_rival_requests (requester_club,target_club,requester_user_id,target_user_id) VALUES ('Ajax','Everton',1,2)")
        self.conn.commit()
        self.guild = SimpleNamespace(id=42)
        self.channel = SimpleNamespace(id=50, send=AsyncMock(return_value=SimpleNamespace(id=60)))
        self.runtime = SimpleNamespace(db_for_guild=lambda guild_id: self.connect())

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()
        feed._locks.clear()

    def respond(self, decision):
        with patch.object(classic.mobile_write_api, '_require_club', return_value='Everton'):
            return classic._respond_classic(self.conn, {'user_id': 2}, {'request_id': 1, 'decision': decision})

    async def test_accept_queues_until_commit_and_announces_once(self):
        self.respond('ACCEPT')
        with (
            patch.object(feed.summary, 'APP', self.runtime),
            patch.object(feed.rumors, '_resolve_summary_channel', AsyncMock(return_value=(self.channel, 'CONFIGURED'))),
            patch.object(feed, '_manager_id', side_effect=[101, 202]),
            patch.object(feed, '_club_emoji', side_effect=['<:ajax:11>', '<:Everton:22>']),
        ):
            # Another connection (the bot worker) cannot see uncommitted links.
            await feed.publish_pending(self.guild)
            self.channel.send.assert_not_awaited()
            self.conn.commit()
            await asyncio.gather(feed.publish_pending(self.guild), feed.publish_pending(self.guild))
            await feed.publish_pending(self.guild)
        self.channel.send.assert_awaited_once()
        kwargs = self.channel.send.call_args.kwargs
        self.assertIn('<:ajax:11> Ajax vs Everton <:Everton:22>', kwargs['embed'].description)
        self.assertIn('DT: <@101>', kwargs['embed'].description)
        self.assertIn('DT: <@202>', kwargs['embed'].description)
        self.assertEqual(kwargs['content'], '🔥 <@101> vs <@202> — ya tienen clásico oficial.')
        self.assertEqual(kwargs['allowed_mentions'].to_dict(), {'parse': ['users']})
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM classic_market_outbox').fetchone()[0], 0)

    async def test_reject_does_not_queue(self):
        self.respond('REJECT')
        self.conn.commit()
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM classic_market_outbox').fetchone()[0], 0)

    async def test_rollback_does_not_queue(self):
        self.respond('ACCEPT')
        self.conn.rollback()
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM classic_market_outbox').fetchone()[0], 0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM classic_rivals').fetchone()[0], 0)

    async def test_missing_channel_retries_later(self):
        self.respond('ACCEPT')
        self.conn.commit()
        with patch.object(feed.summary, 'APP', self.runtime), patch.object(feed.rumors, '_resolve_summary_channel', AsyncMock(return_value=(None, 'NOT_FOUND'))):
            await feed.publish_pending(self.guild)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM classic_market_outbox').fetchone()[0], 1)
        with patch.object(feed.summary, 'APP', self.runtime), patch.object(feed.rumors, '_resolve_summary_channel', AsyncMock(return_value=(self.channel, 'CONFIGURED'))):
            await feed.publish_pending(self.guild)
        self.channel.send.assert_awaited_once()

    async def test_failed_send_preserves_link_and_retries(self):
        self.respond('ACCEPT')
        self.conn.commit()
        self.channel.send.side_effect = RuntimeError('offline')
        with patch.object(feed.summary, 'APP', self.runtime), patch.object(feed.rumors, '_resolve_summary_channel', AsyncMock(return_value=(self.channel, 'CONFIGURED'))):
            with self.assertRaises(RuntimeError):
                await feed.publish_pending(self.guild)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM classic_market_outbox').fetchone()[0], 1)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM classic_rivals').fetchone()[0], 1)

    async def test_another_guild_does_not_receive_announcement(self):
        self.respond('ACCEPT')
        self.conn.commit()
        other_path = Path(self.temp.name) / 'other.db'
        def other_db(guild_id):
            self.assertEqual(guild_id, 99)
            return sqlite3.connect(other_path)
        with patch.object(feed.summary, 'APP', SimpleNamespace(db_for_guild=other_db)), patch.object(feed.rumors, '_resolve_summary_channel', AsyncMock()) as resolve:
            await feed.publish_pending(SimpleNamespace(id=99))
            resolve.assert_not_awaited()
