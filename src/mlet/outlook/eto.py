"""ASCE short-reference ETo calculations for weather-ensemble members."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
import math

import numpy as np
from pyfao56 import refet

from mlet.outlook.contracts import OutlookQuantiles, WeatherMember

GridDay = tuple[str, date]


def eto_for_member(member: WeatherMember) -> float:
    """Compute daily ASCE short-reference ETo (mm) for one weather member."""
    eto_mm = float(
        refet.ascedaily(
            "S",
            member.elevation_m,
            member.latitude,
            member.valid_date.timetuple().tm_yday,
            member.solar_mj_m2_day,
            member.tmax_c,
            member.tmin_c,
            vapr=member.vapor_pressure_kpa,
            wndsp=member.wind_m_s,
            wndht=2.0,
        )
    )
    if not math.isfinite(eto_mm) or eto_mm < 0:
        raise ValueError("ASCE ETo must be finite and non-negative")
    return eto_mm


def summarize_members(values: Sequence[float]) -> OutlookQuantiles:
    """Return deterministic p10, p50, and p90 ETo values (mm) for one group."""
    if not values or any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("ETo ensemble must contain finite non-negative values")

    p10, p50, p90 = np.quantile(
        np.asarray(values, dtype=float), (0.1, 0.5, 0.9)
    )
    quantiles = OutlookQuantiles(float(p10), float(p50), float(p90))
    if quantiles.p10 > quantiles.p50 or quantiles.p50 > quantiles.p90:
        raise ValueError("ETo ensemble quantiles must be ordered p10 <= p50 <= p90")
    return quantiles


def summarize_member_groups(
    members: Sequence[WeatherMember],
) -> dict[GridDay, OutlookQuantiles]:
    """Summarize ETo by native-weather-grid identifier and valid UTC date."""
    grouped_values: dict[GridDay, list[float]] = {}
    for member in members:
        group_key = (member.grid_id, member.valid_date)
        grouped_values.setdefault(group_key, []).append(eto_for_member(member))

    summaries: dict[GridDay, OutlookQuantiles] = {}
    for group_key in sorted(grouped_values):
        values = grouped_values[group_key]
        if len(values) < 3:
            grid_id, valid_date = group_key
            raise ValueError(
                "ETo ensemble for "
                f"grid {grid_id!r} on {valid_date.isoformat()} must contain at least "
                "three members"
            )
        summaries[group_key] = summarize_members(values)
    return summaries
