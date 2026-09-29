"""Слэш-команды должны регистрироваться при запуске, иначе Discord отвечает «Приложение не отвечает»."""

import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import discord

from bot.core import SkifBot
from bot.database import Database

EXPECTED = {
    'setup',
    'panel_application',
    'panel_vacation',
    'profile',
    'activity_top',
    'inactive',
    'leaderboard',
    'leaderboard_post',
    'vacation_status_post',
    'inactivity_post',
    'config_show',
    'recruiter_assign',
    'report_event',
    'backup_now',
    'management',
    'my_requests',
}


class CommandRegistrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_setup_hook_registers_all_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(os.path.join(folder, 'test.db'))
            bot = SkifBot(command_prefix='!', intents=discord.Intents.default(), db=db)
            with (
                patch.object(bot.tree, 'sync', new=AsyncMock()),
                patch.object(SkifBot, '_start_health', new=AsyncMock()),
                patch('bot.discord_backup.DiscordBackups.restore', new=AsyncMock()),
                patch('bot.discord_backup.DiscordBackups.watch_commits'),
                patch('discord.ext.tasks.Loop.start'),
            ):
                await bot.setup_hook()
            try:
                self.assertEqual({c.name for c in bot.tree.get_commands()}, EXPECTED)
            finally:
                await db.conn.close()


if __name__ == '__main__':
    unittest.main()
