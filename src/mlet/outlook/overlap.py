"""Forecast-overlap disagreement diagnostic.

Adapted from neuralhydrology's ``forecast_overlap`` mechanism (v1.13.0,
BSD-3-Clause), where the hindcast and forecast models run concurrently for a
number of steps before issue time and their disagreement regularises the loss.

MLET has no training loop to regularise, but the measurement is useful on its
own. Over an overlap window ending before issue time both an observation-driven
and a forecast-driven ETo trajectory exist, so their disagreement is computable
without labels and without spending held-out data.

Two failure directions matter, and the smaller number is the worse one:

- Disagreement above ``OVERLAP_MAD_MAX_MM`` means the forecast and observed
  drivers describe different weather, so treating them as interchangeable across
  the issue-time boundary is not supported.
- Disagreement below ``OVERLAP_MAD_MIN_MM`` means they are effectively the same
  series. A forecast that reproduces observations to within 0.01 mm/day is
  carrying observed information, which is the leakage that
  ``mlet.outlook.namespaces`` types out at the schema level.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from mlet.outlook.contracts import WeatherMember
from mlet.outlook.dates import idaho_local_day_end_utc
from mlet.outlook.eto import eto_for_member

#: Above this mean absolute difference (mm/day) the two driver sets are not
#: describing the same weather.
OVERLAP_MAD_MAX_MM = 1.5

#: Below this mean absolute difference (mm/day) the forecast is reproducing
#: observations too closely to be an independent product.
OVERLAP_MAD_MIN_MM = 0.01


@dataclass(frozen=True)
class OverlapWindow:
    """Paired observation-driven and forecast-driven members before issue time."""

    issue_time: datetime
    overlap_days: int
    observed: tuple[WeatherMember, ...]
    forecast: tuple[WeatherMember, ...]


@dataclass(frozen=True)
class OverlapDiagnostic:
    """Disagreement between the two driver sets over the overlap window."""

    n_days: int
    mean_absolute_difference_mm: float
    bias_mm: float
    max_absolute_difference_mm: float
    verdict: str


def _daily_eto(members: Sequence[WeatherMember]) -> np.ndarray:
    return np.asarray([eto_for_member(member) for member in members], dtype=float)


def evaluate_overlap(window: OverlapWindow) -> OverlapDiagnostic:
    """Measure observation-driven against forecast-driven ETo over the overlap."""
    if window.overlap_days < 1:
        raise ValueError("overlap window must span at least one day")
    if (
        len(window.observed) != window.overlap_days
        or len(window.forecast) != window.overlap_days
    ):
        raise ValueError(
            "overlap window must contain overlap_days members per driver set"
        )

    observed_days = tuple(member.valid_date for member in window.observed)
    forecast_days = tuple(member.valid_date for member in window.forecast)
    if observed_days != forecast_days:
        raise ValueError("overlap driver sets must cover the same valid dates")
    if len(set(observed_days)) != len(observed_days):
        raise ValueError("overlap window must not repeat a valid date")

    for day in observed_days:
        if idaho_local_day_end_utc(day) > window.issue_time:
            raise ValueError("every overlap day must end before issue_time")

    differences = _daily_eto(window.forecast) - _daily_eto(window.observed)
    mad = float(np.mean(np.abs(differences)))
    if mad < OVERLAP_MAD_MIN_MM:
        verdict = "suspiciously_identical"
    elif mad > OVERLAP_MAD_MAX_MM:
        verdict = "inconsistent"
    else:
        verdict = "consistent"
    return OverlapDiagnostic(
        n_days=window.overlap_days,
        mean_absolute_difference_mm=mad,
        bias_mm=float(np.mean(differences)),
        max_absolute_difference_mm=float(np.max(np.abs(differences))),
        verdict=verdict,
    )
