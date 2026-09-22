"""Frozen Idaho-local calendar conventions for regional outlook artifacts.

Every ``valid_date`` in this project denotes the civil calendar day in
``America/Boise``.  Source adapters must label daily aggregates to that same
local day; an unlabeled UTC-day aggregate is not a valid outlook input.  This
small module is the only place issue timestamps become Idaho calendar dates,
which keeps daylight-saving transitions reproducible.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


IDAHO_TIME_ZONE = ZoneInfo("America/Boise")


def idaho_local_date(value: datetime) -> date:
    """Return the Idaho civil date for an aware instant, including DST."""
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Idaho local-date conversion requires an aware datetime")
    return value.astimezone(IDAHO_TIME_ZONE).date()


def outlook_valid_date(issued_at: datetime, lead_day: int) -> date:
    """Return one frozen 1--20 day outlook date from its issue instant."""
    if (
        isinstance(lead_day, bool)
        or not isinstance(lead_day, int)
        or not 1 <= lead_day <= 20
    ):
        raise ValueError("outlook lead_day must be an integer from 1 through 20")
    return idaho_local_date(issued_at) + timedelta(days=lead_day)


def outlook_valid_dates(issued_at: datetime) -> tuple[date, ...]:
    """Return the twenty contiguous Idaho-local forecast dates."""
    return tuple(outlook_valid_date(issued_at, lead_day) for lead_day in range(1, 21))


def idaho_local_day_end_utc(day: date) -> datetime:
    """Return the end of an Idaho civil day as a UTC instant.

    This is used only where an availability timestamp must be later than a
    completed local day.  ``ZoneInfo`` supplies the correct MST/MDT offset.
    """
    if not isinstance(day, date) or isinstance(day, datetime):
        raise ValueError("Idaho day end requires a calendar date")
    return datetime.combine(day, time.max, tzinfo=IDAHO_TIME_ZONE).astimezone(
        timezone.utc
    )
