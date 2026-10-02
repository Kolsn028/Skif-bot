"""Совместимые импорты для команд и регистрации постоянных view.

Хендлеры правим в bot/forms/<раздел>.py. Эти имена оставлены для кода, который всё
ещё импортирует bot.views; custom_id менять не нужно.
"""

from .forms.activities import (
    ActivityClassifyView,
    ActivityReviewView,
    ActivityTypeSelect,
    RejectActivityModal,
)
from .forms.applications import (
    ApplicationModal,
    ApplicationPanelView,
    RecruiterActionSelect,
    RecruiterActionView,
)
from .forms.shared import (
    _id_from_title,
    _thread_name,
)
from .forms.vacations import (
    VacationDecisionView,
    VacationModal,
    VacationPanelView,
)
from .progression import (
    GreenPanelView,
    WarnPanelView,
)

__all__ = [
    'ActivityClassifyView',
    'ActivityReviewView',
    'ActivityTypeSelect',
    'ApplicationModal',
    'ApplicationPanelView',
    'GreenPanelView',
    'RecruiterActionSelect',
    'RecruiterActionView',
    'RejectActivityModal',
    'VacationDecisionView',
    'VacationModal',
    'VacationPanelView',
    'WarnPanelView',
    '_id_from_title',
    '_thread_name',
]
