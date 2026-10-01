"""Личные каналы: регистрация создаёт приватный канал с 7 постоянными ветками и ничего не дублирует."""

import asyncio
import tempfile
import unittest
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from bot import rooms
from bot.database import Database

GUILD = 1
EXPECTED = ['капт', 'взм', 'взз', 'мцл', 'грины', 'контракт', 'варны']


def member(member_id=10, name='Nick'):
    m = MagicMock(spec=discord.Member)
    m.id = member_id
    m.display_name = name
    m.mention = f'<@{member_id}>'
    m.add = None
    return m


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeChannel:
    def __init__(self, cid, name, topic=None, overwrites=None, category=None, fail_threads=False):
        self.id = cid
        self.name = name
        self.topic = topic
        self.overwrites = overwrites
        self.category = category
        self.threads = []
        self.sent = []
        self.deleted = False
        self.fail_threads = fail_threads
        self.jump_url = f'https://discord.com/channels/{GUILD}/{cid}'
        self.mention = f'<#{cid}>'

    async def send(self, **kwargs):
        self.sent.append(kwargs)

    async def create_thread(self, **kwargs):
        if self.fail_threads:
            raise discord.HTTPException(MagicMock(status=500, reason='x'), 'boom')
        thread = MagicMock(spec=discord.Thread)
        thread.id = self.id * 100 + len(self.threads) + 1
        thread.name = kwargs['name']
        thread.parent_id = self.id
        thread.kwargs = kwargs
        thread.send = AsyncMock()
        thread.add_user = AsyncMock()
        self.threads.append(thread)
        return thread

    async def archived_threads(self, limit=None):
        return
        yield

    async def delete(self, **kwargs):
        self.deleted = True


class FakeCategory:
    def __init__(self, cid, name, count=0):
        self.id = cid
        self.name = name
        self.channels = [object()] * count


class FakeGuild:
    def __init__(self):
        self.id = GUILD
        self.default_role = Obj(id=GUILD)
        self.me = Obj(id=999)
        self.categories = []
        self.text_channels = []
        self.channels = []
        self.created_categories = []
        self.fail_threads = False
        self._next = 1000

    def get_role(self, rid):
        return None

    def get_channel(self, cid):
        return next((c for c in self.text_channels if c.id == cid), None)

    def get_thread(self, tid):
        return next((t for c in self.text_channels for t in c.threads if t.id == tid), None)

    async def fetch_channel(self, tid):
        raise discord.NotFound(MagicMock(status=404, reason='x'), 'nope')

    async def create_category(self, name, **kwargs):
        self._next += 1
        category = FakeCategory(self._next, name)
        self.categories.append(category)
        self.created_categories.append(category)
        return category

    async def create_text_channel(self, name, *, category=None, topic=None, overwrites=None, **kwargs):
        self._next += 1
        channel = FakeChannel(self._next, name, topic, overwrites, category, self.fail_threads)
        self.text_channels.append(channel)
        self.channels.append(channel)
        return channel


class RoomsBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(self.tmp.name + '/test.db')
        await self.db.connect()
        self.bot = SimpleNamespace(
            db=self.db,
            user=SimpleNamespace(id=777),
            operation_locks=defaultdict(asyncio.Lock),
            is_family_member=AsyncMock(return_value=True),
            now_iso=lambda: '2026-10-01T00:00:00+00:00',
        )
        self.guild = FakeGuild()

    async def asyncTearDown(self):
        await self.db.close()
        self.tmp.cleanup()


class Rooms(RoomsBase):
    async def test_registration_creates_private_channel_with_seven_threads(self):
        m = member()
        channel, created = await rooms.register_member(self.bot, self.guild, m)
        self.assertTrue(created)
        self.assertEqual([t.name for t in channel.threads], EXPECTED)
        self.assertFalse(channel.overwrites[self.guild.default_role].view_channel)
        self.assertTrue(channel.overwrites[m].view_channel)
        self.assertEqual(channel.topic, f'skif:room:777:{GUILD}:10')
        self.assertEqual(len(channel.sent), 1)  # приветствие с кнопкой личного меню
        self.assertTrue(all(t.kwargs['auto_archive_duration'] == 10080 for t in channel.threads))
        row = await self.db.get_room(GUILD, 10)
        self.assertEqual(row['channel_id'], channel.id)
        self.assertEqual(sorted(row['threads']), sorted(['capt', 'vzm', 'vzz', 'mcl', 'green', 'contract', 'warn']))

    async def test_second_registration_does_not_duplicate(self):
        m = member()
        first, _ = await rooms.register_member(self.bot, self.guild, m)
        second, created = await rooms.register_member(self.bot, self.guild, m)
        self.assertFalse(created)
        self.assertIs(first, second)
        self.assertEqual(len(second.threads), 7)
        self.assertEqual(len(self.guild.text_channels), 1)

    async def test_full_category_overflows_into_next_one(self):
        self.guild.categories = [FakeCategory(1, 'SKIF • ЛИЧНЫЕ', 50), FakeCategory(2, 'SKIF • СОСТАВ', 3)]
        channel, _ = await rooms.register_member(self.bot, self.guild, member())
        self.assertEqual([c.name for c in self.guild.created_categories], ['SKIF • ЛИЧНЫЕ 2'])
        self.assertEqual(channel.category.name, 'SKIF • ЛИЧНЫЕ 2')
        second, _ = await rooms.register_member(self.bot, self.guild, member(11, 'Other'))
        self.assertEqual(second.category.name, 'SKIF • ЛИЧНЫЕ 2')
        self.assertEqual(len(self.guild.created_categories), 1)


if __name__ == '__main__':
    unittest.main()


class RoomSearchPanel(RoomsBase):
    def hai(self):
        high = member(30, 'Hai')
        high.guild = SimpleNamespace(owner_id=0)
        high.get_role = lambda rid: object() if rid == 5 else None
        return high

    def interaction(self, user):
        i = MagicMock(spec=discord.Interaction)
        i.user = user
        i.guild_id = GUILD
        self.guild.get_member = lambda uid: None
        i.guild = self.guild
        i.response = SimpleNamespace(send_message=AsyncMock())
        return i

    async def test_high_staff_gets_link_from_menu(self):
        from bot.room_search import RoomSearchView

        target = member(20, 'Target')
        channel, _ = await rooms.register_member(self.bot, self.guild, target)
        await self.db.set_config(GUILD, high_staff_role_id=5)
        view = RoomSearchView(self.bot)
        i = self.interaction(self.hai())
        select = SimpleNamespace(values=[target])
        await RoomSearchView.pick(view, i, select)
        self.assertIn(channel.mention, i.response.send_message.await_args.args[0])

    async def test_non_high_staff_denied(self):
        from bot.room_search import RoomSearchView

        await self.db.set_config(GUILD, high_staff_role_id=5)
        view = RoomSearchView(self.bot)
        recruit = member(31, 'Recruit')
        recruit.guild = SimpleNamespace(owner_id=0)
        recruit.get_role = lambda rid: None
        i = self.interaction(recruit)
        select = SimpleNamespace(values=[member(20, 'Target')])
        await RoomSearchView.pick(view, i, select)
        self.assertIn('⛔', i.response.send_message.await_args.args[0])
