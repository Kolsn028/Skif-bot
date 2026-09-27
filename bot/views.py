"""Compatibility imports for existing commands and persistent view registration.

Edit handlers in bot/forms/<feature>.py. Keep these names available for callers
that still import bot.views; no Discord custom_id changes are needed.
"""

from .forms.applications import (
    ApplicationModal,
    ApplicationPanelView,
    RecruiterActionSelect,
    RecruiterActionView,
)
from .forms.vacations import (
    VacationModal,
    VacationPanelView,
    VacationDecisionView,
)
from .progression import (
    GreenPanelView,
    WarnPanelView,
)
from .forms.activities import (
    ActivityTypeSelect,
    ActivityClassifyView,
    RejectActivityModal,
    ActivityReviewView,
)
from .forms.shared import (
    _id_from_title,
    _thread_name,
)

__all__ = ['ApplicationModal', 'ApplicationPanelView', 'RecruiterActionSelect', 'RecruiterActionView', 'VacationModal', 'VacationPanelView', 'VacationDecisionView', 'GreenPanelView', 'WarnPanelView', 'ActivityTypeSelect', 'ActivityClassifyView', 'RejectActivityModal', 'ActivityReviewView', '_id_from_title', '_thread_name']
