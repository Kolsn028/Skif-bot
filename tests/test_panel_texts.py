"""Panel texts must fit Discord limits and keep sentences separated."""

import re
import unittest

from bot.progression import contract_panel_embed, green_panel_embed, promotion_panel_embed, warn_panel_embed
from bot.ui import application_panel_embed, vacation_panel_embed

PANELS = (
    contract_panel_embed,
    green_panel_embed,
    promotion_panel_embed,
    warn_panel_embed,
    application_panel_embed,
    vacation_panel_embed,
)


class PanelTextsTest(unittest.TestCase):
    def test_panels_fit_discord_limits(self):
        for build in PANELS:
            embed = build()
            with self.subTest(panel=build.__name__):
                self.assertLessEqual(len(embed.title or ''), 256)
                self.assertLessEqual(len(embed.description or ''), 4096)
                for field in embed.fields:
                    self.assertLessEqual(len(field.name), 256)
                    self.assertLessEqual(len(field.value), 1024)

    def test_no_missing_space_after_period(self):
        for build in PANELS:
            embed = build()
            text = f'{embed.title}\n{embed.description}\n' + '\n'.join(f.value for f in embed.fields)
            with self.subTest(panel=build.__name__):
                self.assertIsNone(re.search(r'[а-яё]\.[А-ЯЁ]', text), text)


if __name__ == '__main__':
    unittest.main()


class ApplicationCardTest(unittest.IsolatedAsyncioTestCase):
    def card(self):
        from types import SimpleNamespace as NS

        from bot.forms.applications import build_application_card

        user = NS(mention='<@1>', id=1, display_name='Иван', display_avatar=NS(url='https://example.com/a.png'))
        return build_application_card(user, 7, 'Иван, 19', 'Год', '', '45 lvl', 'Не состоял')

    def test_card_layout_and_limits(self):
        e = self.card()
        self.assertEqual([f.name for f in e.fields][-2:], ['Статус', 'Ответственный'])
        self.assertLessEqual(len(e), 6000)
        self.assertEqual([f.inline for f in e.fields[:3]], [True, True, True])
        self.assertEqual(e.fields[5].value, '🟡 На рассмотрении')

    async def test_status_update_changes_only_status(self):
        from unittest.mock import AsyncMock, MagicMock

        from bot.recruiting import set_card_status

        message = MagicMock()
        message.embeds = [self.card()]
        message.edit = AsyncMock()
        await set_card_status(message, '✅ Принят', 0x3BAA72)
        embed = message.edit.await_args.kwargs['embed']
        self.assertEqual(embed.fields[5].value, '✅ Принят')
        self.assertEqual(embed.fields[6].name, 'Ответственный')
        self.assertTrue(embed.fields[5].inline)
