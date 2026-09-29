"""Личный кабинет: общая панель, личное меню, доступ и совместимость старых кнопок хаба."""

import asyncio
import tempfile
import unittest
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from bot import hub
from bot.database import Database
from bot.registry import persistent_views

GUILD = 1


def member(member_id=10, roles=()):
    role_ids = {r.id: r for r in roles}
    m = MagicMock(spec=discord.Member)
    m.id = member_id
    m.display_name = 'Nick'
    m.display_avatar = SimpleNamespace(url='https://example.com/a.png')
    m.joined_at = datetime.now(timezone.utc) - timedelta(days=3)
    m.roles = [
        SimpleNamespace(id=0, name='@everyone', is_default=lambda: True),
        *[SimpleNamespace(id=r.id, name=r.name, is_default=lambda: False) for r in roles],
    ]
    m.get_role = lambda rid: role_ids.get(rid)
    return m


class Hub(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(self.tmp.name + '/test.db')
        await self.db.connect()
        await self.db.set_config(GUILD, accepted_role_id=500, main_role_id=600)
        self.bot = SimpleNamespace(db=self.db, operation_locks=defaultdict(asyncio.Lock), is_family_member=AsyncMock(return_value=True))
        self.guild = SimpleNamespace(id=GUILD)
        self.academy = SimpleNamespace(id=500, name='Academy')

    async def asyncTearDown(self):
        await self.db.close()
        self.tmp.cleanup()

    async def add_progress(self, kind, status='pending', thread=100, details='x'):
        await self.db.conn.execute(
            'INSERT INTO progress_requests(guild_id,member_id,kind,thread_id,details,created_at,status) VALUES (?,?,?,?,?,?,?)',
            (GUILD, 10, kind, thread, details, datetime.now(timezone.utc).isoformat(), status),
        )
        await self.db.conn.commit()

    def interaction(self, user=None, guild_id=GUILD):
        i = MagicMock(spec=discord.Interaction)
        i.user = user or member()
        i.guild_id = guild_id
        i.guild = self.guild
        i.response = SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock(), send_modal=AsyncMock())
        i.followup = SimpleNamespace(send=AsyncMock())
        i.edit_original_response = AsyncMock()
        return i

    def fields(self, embed):
        return {f.name: f.value for f in embed.fields}

    async def test_panel_has_one_button_and_legacy_ids_stay_registered(self):
        self.assertEqual([c.custom_id for c in hub.ProfileHubView(self.bot).children], ['skif:hub:me'])
        legacy = [c.custom_id for c in hub.LegacyHubView(self.bot).children]
        self.assertEqual(legacy, ['skif:hub:green', 'skif:hub:warn', 'skif:hub:contract', 'skif:hub:promotion', 'skif:hub:tier'])
        registered = {c.custom_id for v in persistent_views(MagicMock()) for c in v.children if getattr(c, 'custom_id', None)}
        self.assertTrue({'skif:hub:me', *legacy} <= registered)

    async def test_menu_opens_personally_for_each_member(self):
        i = self.interaction(member(10, [self.academy]))
        await hub.ProfileHubView(self.bot).me.callback(i)
        kwargs = i.followup.send.await_args.kwargs
        self.assertTrue(kwargs['ephemeral'])
        self.assertIn('Nick', kwargs['embed'].title)
        self.assertIs(kwargs['view'].origin, i)

    async def test_stranger_cannot_open_menu(self):
        self.bot.is_family_member.return_value = False
        i = self.interaction()
        await hub.ProfileHubView(self.bot).me.callback(i)
        i.followup.send.assert_not_awaited()
        self.assertTrue(i.response.send_message.await_args.kwargs['ephemeral'])

    async def test_menu_shows_path_progress_and_open_requests(self):
        await self.add_progress('contract', 'approved', 101, '**Помощь** • a\nСобытие: 1')
        await self.add_progress('contract', 'approved', 102, '**Активация** • b\nСобытие: 2')
        await self.add_progress('green', 'pending', 103)
        m = member(10, [self.academy])
        embed, view = await hub.build_menu(self.bot, self.guild, m)
        fields = self.fields(embed)
        path = fields['📈 ПУТЬ К 3 РАНГУ']
        self.assertIn('**1/10**', path)  # одна помощь: активация не считается
        self.assertIn('<#103>', fields['📂 ОТКРЫТЫЕ ЗАЯВКИ'])
        self.assertTrue(view.green.disabled)
        self.assertFalse(view.warn.disabled)

    async def test_main_rank_has_no_path_and_promotion_is_locked(self):
        main = SimpleNamespace(id=600, name='Skif')
        embed, view = await hub.build_menu(self.bot, self.guild, member(10, [main]))
        self.assertNotIn('📈 ПУТЬ К 3 РАНГУ', self.fields(embed))
        self.assertTrue(view.promotion.disabled)

    async def test_tier_request_open_to_family_and_not_configured_elsewhere(self):
        view = hub.MemberMenuView(self.bot, 10, {**await hub.collect(self.bot, self.guild, member(10, [self.academy])), 'tiers_here': True})
        i = self.interaction()
        await view.tier.callback(i)
        self.assertIsInstance(i.response.send_message.await_args.kwargs['view'], hub.TierChoiceView)
        other = hub.MemberMenuView(self.bot, 10, {**await hub.collect(self.bot, self.guild, member()), 'tiers_here': False})
        self.assertTrue(other.tier.disabled)

    async def test_forms_check_family_access_on_click(self):
        self.bot.is_family_member.return_value = False
        for kind in ('green', 'warn', 'contract', 'promotion', 'tier'):
            with self.subTest(kind=kind):
                i = self.interaction()
                await hub.open_form(self.bot, i, kind)
                i.response.send_modal.assert_not_awaited()
                self.assertEqual(i.response.send_message.await_args.args[0], 'Доступно участникам семьи.')

    async def test_menu_belongs_to_its_owner(self):
        view = hub.MemberMenuView(self.bot, 10, await hub.collect(self.bot, self.guild, member()))
        other = self.interaction(member(99))
        self.assertFalse(await view.interaction_check(other))
        self.assertTrue(await view.interaction_check(self.interaction(member(10))))

    async def test_history_and_back(self):
        await self.add_progress('contract', 'approved', 101, '**Помощь** • a\nСобытие: 1')
        view = hub.MemberMenuView(self.bot, 10, await hub.collect(self.bot, self.guild, member()))
        view.origin = 'origin'
        i = self.interaction()
        await view.history.callback(i)
        shown = i.edit_original_response.await_args.kwargs
        self.assertIn('Помощь', shown['embed'].description)
        self.assertIsInstance(shown['view'], hub.HistoryView)
        self.assertEqual(shown['view'].origin, 'origin')
        i2 = self.interaction()
        await shown['view'].back.callback(i2)
        self.assertIsInstance(i2.edit_original_response.await_args.kwargs['view'], hub.MemberMenuView)


if __name__ == '__main__':
    unittest.main()
