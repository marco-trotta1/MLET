"""Freeze the GEFSv12 reforecast issues used for the ETo manuscript study."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone


def weekly_wednesday_00z_issues(
    first_date: date, last_date: date
) -> tuple[datetime, ...]:
    """Return every Wednesday 00Z issue inside one inclusive interval.

    This schedule is selected before downloading or scoring reforecasts. It is
    intentionally independent of forecast data, station observations, and any
    performance result.
    """
    if not isinstance(first_date, date) or isinstance(first_date, datetime):
        raise ValueError("first_date must be a calendar date")
    if not isinstance(last_date, date) or isinstance(last_date, datetime):
        raise ValueError("last_date must be a calendar date")
    if first_date > last_date:
        raise ValueError("first_date must not be after last_date")
    days_to_wednesday = (2 - first_date.weekday()) % 7
    issue_date = first_date + timedelta(days=days_to_wednesday)
    issues = []
    while issue_date <= last_date:
        issues.append(datetime.combine(issue_date, time.min, tzinfo=timezone.utc))
        issue_date += timedelta(days=7)
    if not issues:
        raise ValueError("historical interval contains no Wednesday 00Z issue")
    return tuple(issues)
