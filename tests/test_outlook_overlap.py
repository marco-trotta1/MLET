"""Non-scientific deterministic checks for the forecast-overlap diagnostic."""

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from mlet.outlook.contracts import WeatherMember
from mlet.outlook.overlap import (
    OVERLAP_MAD_MAX_MM,
    OVERLAP_MAD_MIN_MM,
    OverlapDiagnostic,
    OverlapWindow,
    evaluate_overlap,
)

ISSUE = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def _member(day: date, *, member_id: str, tmax_c: float) -> WeatherMember:
    return WeatherMember(
        grid_id="fixture-grid-a",
        latitude=43.6175,
        longitude=-116.1997,
        elevation_m=824.0,
        member_id=member_id,
        issued_at=ISSUE,
        valid_date=day,
        tmax_c=tmax_c,
        tmin_c=15.0,
        vapor_pressure_kpa=1.2,
        wind_m_s=2.5,
        solar_mj_m2_day=28.0,
        precip_mm=0.0,
    )


def _window(*, forecast_tmax: float) -> OverlapWindow:
    days = (date(2026, 7, 12), date(2026, 7, 13), date(2026, 7, 14))
    return OverlapWindow(
        issue_time=ISSUE,
        overlap_days=3,
        observed=tuple(_member(d, member_id="obs", tmax_c=33.0) for d in days),
        forecast=tuple(_member(d, member_id="fc", tmax_c=forecast_tmax) for d in days),
    )


def test_identical_drivers_are_flagged_as_suspiciously_identical() -> None:
    """Zero disagreement means the forecast is carrying observed information."""
    diagnostic = evaluate_overlap(_window(forecast_tmax=33.0))
    assert isinstance(diagnostic, OverlapDiagnostic)
    assert diagnostic.n_days == 3
    assert diagnostic.mean_absolute_difference_mm < OVERLAP_MAD_MIN_MM
    assert diagnostic.verdict == "suspiciously_identical"


def test_plausible_forecast_error_is_consistent() -> None:
    diagnostic = evaluate_overlap(_window(forecast_tmax=34.5))
    assert OVERLAP_MAD_MIN_MM <= diagnostic.mean_absolute_difference_mm <= OVERLAP_MAD_MAX_MM
    assert diagnostic.verdict == "consistent"
    assert diagnostic.bias_mm > 0  # warmer forecast drives higher ETo


def test_large_disagreement_is_inconsistent() -> None:
    diagnostic = evaluate_overlap(_window(forecast_tmax=48.0))
    assert diagnostic.mean_absolute_difference_mm > OVERLAP_MAD_MAX_MM
    assert diagnostic.verdict == "inconsistent"


def test_overlap_must_end_before_issue_time() -> None:
    window = _window(forecast_tmax=34.5)
    after_issue = replace(
        window,
        observed=window.observed + (_member(date(2026, 7, 16), member_id="obs", tmax_c=33.0),),
        forecast=window.forecast + (_member(date(2026, 7, 16), member_id="fc", tmax_c=34.5),),
        overlap_days=4,
    )
    with pytest.raises(ValueError, match="before issue_time"):
        evaluate_overlap(after_issue)


def test_mismatched_dates_are_rejected() -> None:
    window = _window(forecast_tmax=34.5)
    shifted = replace(
        window,
        forecast=tuple(
            replace(member, valid_date=date(2026, 7, 11)) for member in window.forecast
        ),
    )
    with pytest.raises(ValueError, match="same valid dates"):
        evaluate_overlap(shifted)
