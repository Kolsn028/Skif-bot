"""Unified access control tests - combined from test_access_policy.py, test_setup_access.py, test_leave_role_only.py"""
import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault('TIER_GUILD_ID', '1')
os.environ.setdefault('TIERCHECK_ROLE_ID', '42')
os.environ.setdefault('TIER_1_ROLE_ID', '101')
os.environ.setdefault('TIER_2_ROLE_ID', '102')
os.environ.setdefault('TIER_3_ROLE_ID', '103')

import discord
from discord import app_commands
from discord.ext import commands

from bot import access
from bot.commands import register_commands
from bot.leave import begin_leave, restore_leave

CFG = dict(leader_role_id=1, dep_leader_role_id=2, high_staff_role_id=3,
           recruiter_role_id=4, main_role_id=5, accepted_role_id=6,
           family_role_id=7, guest_role_id=8, role_schema_version=2)


def member(roles=(), uid=10, admin=False):
    return NS(id=uid, guild=NS(id=access.TIER_GUILD_ID, owner_id=99),
              get_role=lambda rid: rid if rid in roles else None,
              guild_permissions=NS(administrator=admin))


class AccessControlTest(unittest.TestCase):
    """Tests from test_access_policy.py"""
    
    def test_matrix_including_admin_and_owner(self):
        for role in range(1, 9):
            m = member([role], admin=True)
            with self.subTest(role=role):
                for check in (access.may_recruit, access.may_review_reports, access.may_promote):
                    self.assertEqual(bool(check(m, CFG)), role <= 4)
                for check in (access.may_manage_events, access.may_view_profiles, access.may_review_vacation):
                    self.assertEqual(bool(check(m, CFG)), role <= 3)
                self.assertFalse(access.may_review_tiers(m, access.TIER_GUILD_ID))
        owner = member(uid=99)
        self.assertTrue(access.may_manage_events(owner, CFG))
        self.assertFalse(access.may_review_tiers(owner, access.TIER_GUILD_ID))
        checker = member([access.TIERCHECK_ROLE_ID])
        self.assertTrue(access.may_review_tiers(checker, access.TIER_GUILD_ID))
        self.assertFalse(access.may_review_tiers(checker, 123))

    def test_assignment_override_preserves_existing_rule(self):
        app = {'assigned_to': 11}
        for roles, uid, admin, expected in [([4],10,False,False),([4],11,False,True),
                ([3],10,False,False),([2],10,False,True),([4],10,True,True),([],10,True,False)]:
            with self.subTest(roles=roles, uid=uid, admin=admin):
                self.assertEqual(bool(access.may_decide_application(member(roles,uid,admin),CFG,app)),expected)

    def test_attendance_requires_organizer_or_leadership(self):
        event = {'creator_id': 11}
        self.assertFalse(access.may_confirm_attendance(member([3]), CFG, event))
        self.assertTrue(access.may_confirm_attendance(member([3], uid=11), CFG, event))
        self.assertFalse(access.may_confirm_attendance(member([4], uid=11), CFG, event))
        for roles, uid in [([1], 10), ([2], 10), ([], 99)]:
            self.assertTrue(access.may_confirm_attendance(member(roles, uid), CFG, event))

    def test_setup_name_lookup_only_before_configuration(self):
        resolver = lambda guild,key: NS(id=1) if key=='leader_role_id' else None
        self.assertTrue(access.may_setup(member([1]), {}, resolver))
        self.assertFalse(access.may_setup(member([1]), {'role_schema_version':2}, resolver))
        self.assertFalse(access.may_setup(member([3]), {}, resolver))
        self.assertFalse(access.may_setup(member(admin=True), {}, resolver))
        self.assertFalse(access.may_setup(member(uid=99), {}, resolver))
        self.assertFalse(access.may_setup(member([1]), {'leader_role_id':9}, resolver))


class SetupAccessTest(unittest.IsolatedAsyncioTestCase):
    """Tests from test_setup_access.py"""
    
    async def asyncSetUp(self):
        self.bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())
        self.cfg = dict(role_schema_version=2, leader_role_id=1,
                        dep_leader_role_id=2, high_staff_role_id=3,
                        recruiter_role_id=4, main_role_id=5)
        self.bot.db = NS(get_config=AsyncMock(return_value=self.cfg))
        register_commands(self.bot)

    async def asyncTearDown(self):
        await self.bot.close()

    def interaction(self, role_id, owner=False):
        member = MagicMock(spec=discord.Member)
        member.id = 99 if owner else 10
        member.guild = NS(owner_id=99)
        member.get_role.side_effect = lambda rid: object() if rid == role_id else None
        return NS(user=member, guild_id=100, guild=member.guild,
            response=NS(defer=AsyncMock()),
            followup=NS(send=AsyncMock()))

    async def test_only_leader_can_setup_and_auto_is_removed(self):
        self.assertIsNone(self.bot.tree.get_command('setup_auto'))
        command = self.bot.tree.get_command('setup')
        self.assertTrue({'main','guest','test','family','high'}.issubset({p.name for p in command.parameters}))
        self.assertTrue(await command.checks[0](self.interaction(1)))
        for role_id in (2, 3, 4, 5, None):
            for owner in (False, True):
                i = self.interaction(role_id, owner=owner)
                i.user.guild_permissions = discord.Permissions(administrator=True)
                with self.assertRaises(app_commands.CheckFailure):
                    await command.checks[0](i)
        selected = object()
        with patch('bot.provisioning.provision', new_callable=AsyncMock) as provision:
            await command.callback(self.interaction(1), main=selected)
            self.assertIs(provision.call_args.args[2]['main_role_id'], selected)

    async def test_guild_sync_removes_old_auto_command(self):
        import asyncio
        from collections import defaultdict
        from bot.core import SkifBot
        
        guild = NS(id=100)
        stale = NS(name='setup_auto', options=[])
        setup = NS(name='setup', options=[NS(name=n) for n in ('main','guest','test','family')])
        registered = [setup, stale]
        async def sync(**kwargs):
            registered[:] = [setup]
        tree = NS(copy_global_to=MagicMock(), sync=AsyncMock(side_effect=sync),
                               fetch_commands=AsyncMock(side_effect=lambda **kw: registered))
        bot = NS(tree=tree, operation_locks=defaultdict(asyncio.Lock))
        await SkifBot.sync_guild_commands(bot, guild)
        self.assertEqual([c.name for c in registered], ['setup'])
        self.assertEqual(bot._commands_synced, {100})


class LeaveRoleOnlyTest(unittest.IsolatedAsyncioTestCase):
    """Tests from test_leave_role_only.py"""
    
    async def test_new_leave_only_toggles_leave_role_and_preserves_saved_id(self):
        leave = MagicMock(spec=discord.Role)
        leave.id = 7
        leave.managed = False
        leave.is_default.return_value = False
        leave.__ge__.return_value = False
        member = NS(add_roles=AsyncMock(), remove_roles=AsyncMock())
        guild = NS(id=1, me=NS(top_role=object()),
            fetch_member=AsyncMock(return_value=member), get_role=lambda rid: leave if rid == 7 else None)
        vac = dict(id=1, member_id=10, role_snapshot=None, status='pending')
        async def update(vid, **fields):
            vac.update(fields)
        cfg = {'vacation_role_id': 7}
        bot = NS(now_iso=lambda: '2026-09-14T00:00:00+00:00',
            db=NS(get_config=AsyncMock(return_value=cfg),
                update_vacation=AsyncMock(side_effect=update),
                get_vacation=AsyncMock(side_effect=lambda vid: dict(vac)))
        )
        await begin_leave(bot, guild, dict(vac))
        self.assertEqual(member.add_roles.call_args.args, (leave,))
        member.remove_roles.assert_not_awaited()
        self.assertEqual(vac['status'], 'approved')
        cfg['vacation_role_id'] = 88
        member.add_roles.reset_mock()
        await restore_leave(bot, guild, dict(vac))
        member.add_roles.assert_not_awaited()
        self.assertEqual(member.remove_roles.call_args.args, (leave,))
        self.assertEqual(vac['status'], 'returned')


if __name__ == '__main__':
    unittest.main()
