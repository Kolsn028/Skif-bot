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
