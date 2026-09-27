"""Compatibility imports for existing commands and persistent view registration.

Edit handlers in bot/forms/<feature>.py. Keep these names available for callers
that still import bot.views; no Discord custom_id changes are needed.
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

__all__ = ['ActivityClassifyView', 'ActivityReviewView', 'ActivityTypeSelect', 'ApplicationModal', 'ApplicationPanelView', 'GreenPanelView', 'RecruiterActionSelect', 'RecruiterActionView', 'RejectActivityModal', 'VacationDecisionView', 'VacationModal', 'VacationPanelView', 'WarnPanelView', '_id_from_title', '_thread_name']
