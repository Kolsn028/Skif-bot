"""Единый список постоянных панелей (persistent views).

Каждая View с timeout=None и статичными custom_id обязана быть здесь: после перезапуска
бота Discord вызывает только зарегистрированные представления, иначе кнопка отвечает
«Ошибка взаимодействия». Проверяет tests/test_persistent_views.py.
"""


def persistent_views(bot):
    from .dashboard import ManagementView
    from .events import EventPanelView, EventView
    from .leave import ReturnDecisionView
    from .profiles import ProfileLauncher
    from .progression import ContractPanelView, GreenPanelView, ProgressReviewView, PromotionPanelView, WarnPanelView
    from .tiers import TierPanelView, TierReviewView
    from .views import (
        ActivityClassifyView,
        ActivityReviewView,
        ApplicationPanelView,
        RecruiterActionView,
        VacationDecisionView,
        VacationPanelView,
    )

    return [
        TierPanelView(bot),
        TierReviewView(bot),
        ManagementView(bot),
        ApplicationPanelView(bot),
        RecruiterActionView(bot),
        VacationPanelView(bot),
        VacationDecisionView(bot),
        ActivityClassifyView(bot),
        ActivityReviewView(bot),
        ContractPanelView(bot),
        GreenPanelView(bot),
        WarnPanelView(bot),
        PromotionPanelView(bot),
        ProgressReviewView(bot),
        ProfileLauncher(bot),
        ReturnDecisionView(bot),
        EventPanelView(bot),
        EventView(bot, legacy=True),
    ]
