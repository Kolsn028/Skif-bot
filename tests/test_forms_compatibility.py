"""Existing Discord messages must keep working after moving their handlers."""
import importlib
import unittest

from bot import views


class PersistentFormsTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_message_component_ids_still_register(self):
        expected = {
            'ApplicationPanelView': ['skif:application:open', 'skif:application:mine'],
            'RecruiterActionView': ['skif:recruiter:claim', 'skif:recruiter:release', 'skif:recruiter:action'],
            'VacationPanelView': ['skif:vacation:open', 'skif:vacation:return'],
            'VacationDecisionView': ['skif:vacation:approve', 'skif:vacation:reject'],
            'ActivityClassifyView': ['skif:activity:type'],
            'ActivityReviewView': ['skif:activity:approve', 'skif:activity:reject', 'skif:activity:reclassify'],
        }
        expected.update({
            'GreenPanelView': ['skif:green:open'],
            'WarnPanelView': ['skif:warn:open'],
        })
        registered = []
        for name, ids in expected.items():
            with self.subTest(view=name):
                view = getattr(views, name)(None)
                self.assertTrue(view.is_persistent())
                self.assertEqual([item.custom_id for item in view.children], ids)
                registered.extend(ids)
        self.assertEqual(len(registered), len(set(registered)))

    async def test_old_imports_refer_to_the_same_handlers(self):
        groups = {
            'applications': ['ApplicationModal', 'ApplicationPanelView', 'RecruiterActionSelect', 'RecruiterActionView'],
            'vacations': ['VacationModal', 'VacationPanelView', 'VacationDecisionView'],
                        'activities': ['ActivityTypeSelect', 'ActivityClassifyView', 'RejectActivityModal', 'ActivityReviewView'],
        }
        for module_name, names in groups.items():
            module = importlib.import_module('bot.forms.' + module_name)
            for name in names:
                with self.subTest(handler=name):
                    self.assertIs(getattr(views, name), getattr(module, name))
        from bot import progression as progression_module
        for name in ('GreenPanelView', 'WarnPanelView'):
            with self.subTest(handler=name):
                self.assertIs(getattr(views, name), getattr(progression_module, name))
