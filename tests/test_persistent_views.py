"""Every persistent panel button must be registered, otherwise it breaks after a restart."""

import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from bot.registry import persistent_views

ROOT = Path(__file__).resolve().parent.parent / 'bot'


class PersistentViewsTest(unittest.IsolatedAsyncioTestCase):
    async def test_all_static_custom_ids_are_registered(self):
        in_code = set()
        for path in ROOT.rglob('*.py'):
            in_code.update(re.findall(r"custom_id='(skif:[^']+)'", path.read_text(encoding='utf-8')))
        registered = {item.custom_id for view in persistent_views(MagicMock()) for item in view.children if getattr(item, 'custom_id', None)}
        self.assertEqual(sorted(in_code - registered), [], 'Кнопки без зарегистрированной панели')


if __name__ == '__main__':
    unittest.main()
