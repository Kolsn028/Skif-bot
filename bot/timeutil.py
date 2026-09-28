from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3), name='MSK')


def msk_today() -> date:
    return datetime.now(MSK).date()
