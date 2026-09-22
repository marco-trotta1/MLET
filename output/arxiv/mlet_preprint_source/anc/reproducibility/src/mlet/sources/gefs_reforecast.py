"""Convert GEFSv12 daily GRIB quantities to canonical ASCE weather inputs.

The GRIB reader is intentionally outside this module. It must select the
documented GEFS messages and aggregate one Idaho local day before it calls this
pure conversion boundary.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from datetime import date, datetime, timedelta, timezone
import math

from mlet.outlook.dates import idaho_local_date


_REQUIRED_FIELDS = {
    "grid_id",
    "latitude",
    "longitude",
    "elevation_m",
    "member_id",
    "valid_date",
    "tmax_k",
    "tmin_k",
    "specific_humidity_kg_kg",
    "surface_pressure_pa",
    "u10_m_s",
    "v10_m_s",
    "shortwave_j_m2_day",
    "precipitation_kg_m2_day",
}
_KELVIN_OFFSET = 273.15
_JOULES_PER_MEGJOULE = 1_000_000.0
_WATER_DENSITY_KG_PER_M3 = 1_000.0
_EPSILON = 0.622
_COMPONENT_STEP_FIELDS = {
    "field",
    "grid_id",
    "latitude",
    "longitude",
    "elevation_m",
    "member_id",
    "interval_start_at",
    "interval_end_at",
    "value",
}
_THREE_HOUR_SECONDS = 10_800
_SIX_HOUR_SECONDS = 21_600
_COMPONENT_SPECS = {
    "tmax_k": (_SIX_HOUR_SECONDS, 150.0, 400.0),
    "tmin_k": (_SIX_HOUR_SECONDS, 150.0, 400.0),
    "specific_humidity_kg_kg": (_THREE_HOUR_SECONDS, 0.0, 0.1),
    "surface_pressure_pa": (_THREE_HOUR_SECONDS, 30_000.0, 110_000.0),
    "u10_m_s": (_THREE_HOUR_SECONDS, -100.0, 100.0),
    "v10_m_s": (_THREE_HOUR_SECONDS, -100.0, 100.0),
    "shortwave_w_m2": (_THREE_HOUR_SECONDS, 0.0, 2_000.0),
    "precipitation_increment_kg_m2": (_SIX_HOUR_SECONDS, 0.0, 10_000.0),
}


def aggregate_gefs_reforecast_steps(
    steps: Iterable[dict[str, object]],
    *,
    valid_dates: Collection[date] | None = None,
) -> list[dict[str, object]]:
    """Aggregate separate GEFS components to strict Idaho-local daily inputs.

    GEFS v12 stores temperature extrema and precipitation in six-hour message
    intervals. It stores humidity, pressure, wind, and shortwave radiation in
    three-hour intervals. MLET assigns each interval to the Idaho civil day
    that contains its midpoint. This keeps an interval ending at local midnight
    in the day it describes and gives four six-hour or eight three-hour values
    per output day across the MST/MDT transition.
    """
    groups: dict[tuple[str, str, str], dict[str, list[dict[str, object]]]] = {}
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or set(step) != _COMPONENT_STEP_FIELDS:
            raise ValueError(
                f"GEFS reforecast component step {index} fields must match the schema exactly"
            )
        field = _text(step["field"], "field")
        try:
            interval_seconds, lower, upper = _COMPONENT_SPECS[field]
        except KeyError as error:
            raise ValueError("GEFS reforecast component field is unsupported") from error
        interval_start = _parse_utc(step["interval_start_at"], "interval_start_at")
        interval_end = _parse_utc(step["interval_end_at"], "interval_end_at")
        if interval_end - interval_start != timedelta(seconds=interval_seconds):
            raise ValueError("GEFS reforecast component interval has the wrong duration")
        _finite(step["value"], field, lower, upper)
        valid_date = idaho_local_date(
            interval_start + timedelta(seconds=interval_seconds / 2.0)
        )
        if valid_dates is not None and valid_date not in valid_dates:
            continue
        valid_date_text = valid_date.isoformat()
        grid_id = _text(step["grid_id"], "grid_id")
        member_id = _text(step["member_id"], "member_id")
        key = (grid_id, member_id, valid_date_text)
        groups.setdefault(key, {}).setdefault(field, []).append(step)

    daily: list[dict[str, object]] = []
    for (grid_id, member_id, valid_date), component_groups in sorted(groups.items()):
        if set(component_groups) != set(_COMPONENT_SPECS):
            raise ValueError("GEFS reforecast day is missing one or more components")
        all_steps = [step for values in component_groups.values() for step in values]
        location = _location(all_steps[0])
        if any(_location(step) != location for step in all_steps[1:]):
            raise ValueError("GEFS reforecast grid coordinates changed within one day")
        for field, values in component_groups.items():
            interval_seconds, _lower, _upper = _COMPONENT_SPECS[field]
            expected_count = 86_400 // interval_seconds
            interval_starts = {
                _parse_utc(value["interval_start_at"], "interval_start_at")
                for value in values
            }
            if len(values) != expected_count or len(interval_starts) != expected_count:
                raise ValueError(
                    "GEFS reforecast day does not contain the required component intervals"
                )
        daily.append(
            {
                "grid_id": grid_id,
                "latitude": location[0],
                "longitude": location[1],
                "elevation_m": location[2],
                "member_id": member_id,
                "valid_date": valid_date,
                "tmax_k": _component_max(component_groups["tmax_k"], "tmax_k"),
                "tmin_k": _component_min(component_groups["tmin_k"], "tmin_k"),
                "specific_humidity_kg_kg": _component_mean(
                    component_groups["specific_humidity_kg_kg"],
                    "specific_humidity_kg_kg",
                ),
                "surface_pressure_pa": _component_mean(
                    component_groups["surface_pressure_pa"], "surface_pressure_pa"
                ),
                "u10_m_s": _component_mean(component_groups["u10_m_s"], "u10_m_s"),
                "v10_m_s": _component_mean(component_groups["v10_m_s"], "v10_m_s"),
                "shortwave_j_m2_day": sum(
                    _finite(step["value"], "shortwave_w_m2", 0.0, 2_000.0)
                    * _THREE_HOUR_SECONDS
                    for step in component_groups["shortwave_w_m2"]
                ),
                "precipitation_kg_m2_day": sum(
                    _finite(
                        step["value"],
                        "precipitation_increment_kg_m2",
                        0.0,
                        10_000.0,
                    )
                    for step in component_groups["precipitation_increment_kg_m2"]
                ),
            }
        )
    return daily


def normalize_gefs_reforecast_daily_rows(
    rows: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    """Convert complete daily GEFS fields to the canonical GEFS row units."""
    converted: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != _REQUIRED_FIELDS:
            raise ValueError(f"GEFS reforecast row {index} fields must match the schema exactly")
        tmax_k = _finite(row["tmax_k"], "tmax_k", 150.0, 400.0)
        tmin_k = _finite(row["tmin_k"], "tmin_k", 150.0, 400.0)
        if tmax_k < tmin_k:
            raise ValueError("GEFS reforecast tmax_k must not be below tmin_k")
        specific_humidity = _finite(
            row["specific_humidity_kg_kg"], "specific_humidity_kg_kg", 0.0, 0.1
        )
        pressure_pa = _finite(row["surface_pressure_pa"], "surface_pressure_pa", 30_000.0, 110_000.0)
        u10_m_s = _finite(row["u10_m_s"], "u10_m_s", -100.0, 100.0)
        v10_m_s = _finite(row["v10_m_s"], "v10_m_s", -100.0, 100.0)
        shortwave_j_m2_day = _finite(
            row["shortwave_j_m2_day"], "shortwave_j_m2_day", 0.0, 100_000_000.0
        )
        precipitation_kg_m2_day = _finite(
            row["precipitation_kg_m2_day"], "precipitation_kg_m2_day", 0.0, 10_000.0
        )
        _require_text(row["grid_id"], "grid_id")
        _require_text(row["member_id"], "member_id")
        _require_date_text(row["valid_date"])
        converted.append(
            {
                "grid_id": row["grid_id"],
                "latitude": _finite(row["latitude"], "latitude", -90.0, 90.0),
                "longitude": _finite(row["longitude"], "longitude", -180.0, 180.0),
                "elevation_m": _finite(row["elevation_m"], "elevation_m", -500.0, 10_000.0),
                "member_id": row["member_id"],
                "valid_date": row["valid_date"],
                "tmax_c": tmax_k - _KELVIN_OFFSET,
                "tmin_c": tmin_k - _KELVIN_OFFSET,
                "vapor_pressure_kpa": _vapor_pressure_kpa(specific_humidity, pressure_pa),
                "wind_m_s": math.hypot(u10_m_s, v10_m_s),
                "solar_mj_m2_day": shortwave_j_m2_day / _JOULES_PER_MEGJOULE,
                "precip_mm": precipitation_kg_m2_day / _WATER_DENSITY_KG_PER_M3 * 1_000.0,
            }
        )
    return converted


def _vapor_pressure_kpa(specific_humidity: float, pressure_pa: float) -> float:
    denominator = _EPSILON + (1.0 - _EPSILON) * specific_humidity
    return specific_humidity * pressure_pa / denominator / 1_000.0


def _finite(value: object, label: str, lower: float, upper: float) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or not lower <= result <= upper:
        raise ValueError(f"{label} is outside its valid range")
    return result


def _require_text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")


def _text(value: object, label: str) -> str:
    _require_text(value, label)
    assert isinstance(value, str)
    return value


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text")
    return parsed.astimezone(timezone.utc)


def _location(step: dict[str, object]) -> tuple[float, float, float]:
    return (
        _finite(step["latitude"], "latitude", -90.0, 90.0),
        _finite(step["longitude"], "longitude", -180.0, 180.0),
        _finite(step["elevation_m"], "elevation_m", -500.0, 10_000.0),
    )


def _component_max(steps: list[dict[str, object]], field: str) -> float:
    _seconds, lower, upper = _COMPONENT_SPECS[field]
    return max(_finite(step["value"], field, lower, upper) for step in steps)


def _component_min(steps: list[dict[str, object]], field: str) -> float:
    _seconds, lower, upper = _COMPONENT_SPECS[field]
    return min(_finite(step["value"], field, lower, upper) for step in steps)


def _component_mean(steps: list[dict[str, object]], field: str) -> float:
    _seconds, lower, upper = _COMPONENT_SPECS[field]
    return sum(_finite(step["value"], field, lower, upper) for step in steps) / len(steps)


def _require_date_text(value: object) -> None:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("valid_date must be YYYY-MM-DD")
