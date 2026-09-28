"""Every persistent panel view must be registered in SkifBot.setup_hook, otherwise its buttons break after a restart."""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'bot'


def persistent_views():
    for path in ROOT.rglob('*.py'):
        source = path.read_text(encoding='utf-8')
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef):
                text = ast.get_source_segment(source, node) or ''
                if 'timeout=None' in text and 'custom_id' in text:
                    yield node.name


class PersistentViewsTest(unittest.TestCase):
    def test_all_persistent_views_are_registered(self):
        core = (ROOT / 'core.py').read_text(encoding='utf-8')
        missing = sorted(name for name in persistent_views() if f'{name}(' not in core)
        self.assertEqual(missing, [], f'Не зарегистрированы в setup_hook: {missing}')


if __name__ == '__main__':
    unittest.main()
