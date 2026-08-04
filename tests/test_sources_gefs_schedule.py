"""Tests for the frozen weekly GEFSv12 hindcast issue schedule."""

from __future__ import annotations

from datetime import date, datetime, timezone

from mlet.sources.gefs_schedule import weekly_wednesday_00z_issues


def test_weekly_wednesday_schedule_is_fixed_before_any_hindcast_skill_is_scored() -> None:
    """Changing the issue weekday or historical bounds changes the experiment."""
    issues = weekly_wednesday_00z_issues(date(2013, 1, 1), date(2019, 12, 31))

    assert issues[0] == datetime(2013, 1, 2, tzinfo=timezone.utc)
    assert issues[-1] == datetime(2019, 12, 25, tzinfo=timezone.utc)
    assert len(issues) == 365
    assert all(issue.weekday() == 2 and issue.hour == 0 for issue in issues)
