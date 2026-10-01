"""Понятные ответы вместо «Ошибка взаимодействия»: ошибки и устаревшие кнопки."""

import sqlite3
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot.core import SkifBot
from bot.interactions import report_error


def interaction(done=False):
    response = MagicMock()
    response.is_done.return_value = done
    response.send_message = AsyncMock()
    return NS(response=response, followup=NS(send=AsyncMock()))


def http_error(status):
    return discord.HTTPException(NS(status=status, reason='x'), 'x')


class ReportErrorTest(unittest.IsolatedAsyncioTestCase):
    async def sent_text(self, error):
        i = interaction()
        await report_error(i, error)
        return i.response.send_message.await_args.args[0]

    async def test_specific_messages(self):
        self.assertIn('ограничил запросы', await self.sent_text(http_error(429)))
        self.assertIn('недоступен', await self.sent_text(http_error(503)))
        self.assertIn('сохранить данные', await self.sent_text(sqlite3.OperationalError('locked')))
        self.assertEqual(await self.sent_text(ValueError('Своё сообщение')), 'Своё сообщение')


class StaleButtonTest(unittest.IsolatedAsyncioTestCase):
    def bot_with(self, custom_ids):
        bot = MagicMock()
        view = NS(children=[NS(custom_id=c) for c in custom_ids])
        type(bot).persistent_views = property(lambda self: [view])
        return bot

    async def run_fallback(self, i, custom_id, known):
        with patch('bot.core.asyncio.sleep', new=AsyncMock()):
            await SkifBot._stale_button_fallback(self.bot_with(known), i, custom_id)

    async def test_unknown_button_gets_explanation(self):
        i = interaction()
        await self.run_fallback(i, 'skif:old:button', ['skif:green:open'])
        self.assertIn('устарела', i.response.send_message.await_args.args[0])

    async def test_known_or_handled_button_is_left_alone(self):
        i = interaction()
        await self.run_fallback(i, 'skif:green:open', ['skif:green:open'])
        i.response.send_message.assert_not_awaited()
        done = interaction(done=True)
        await self.run_fallback(done, 'skif:old:button', [])
        done.response.send_message.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
