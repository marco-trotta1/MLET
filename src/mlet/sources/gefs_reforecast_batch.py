"""Decode one complete verified GEFSv12 issue into daily weather rows."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from mlet.outlook.dates import outlook_valid_dates

from mlet.sources.gefs_grib import (
    decode_gefs_reforecast_grib_member,
    gefs_reforecast_grib_short_names,
)
from mlet.sources.gefs_reforecast_acquisition import GefsReforecastRawObject
from mlet.sources.gefs_reforecast_plan import build_gefs_reforecast_acquisition_plan
from mlet.sources.gefs_reforecast_uri import (
    _HORIZON_SEGMENTS,
    gefs_reforecast_member_ids,
)

_WEATHER_COMPONENTS = (
    "tmax_k",
    "tmin_k",
    "specific_humidity_kg_kg",
    "surface_pressure_pa",
    "u10_m_s",
    "v10_m_s",
    "shortwave_w_m2",
    "precipitation_increment_kg_m2",
)


def decode_gefs_reforecast_issue(
    raw_objects: Sequence[GefsReforecastRawObject],
    *,
    issue_time: datetime,
    idaho_bbox: tuple[float, float, float, float],
) -> list[dict[str, object]]:
    """Decode a complete, receipt-verified issue for every frozen member.

    The caller must obtain `raw_objects` from
    `load_verified_gefs_reforecast_receipt()`. This function rechecks the
    exact fixed plan before it opens a GRIB file.
    """
    issue = _require_utc(issue_time)
    issue_objects = tuple(
        object_plan
        for object_plan in raw_objects
        if object_plan.issue_time == issue
    )
    _require_exact_issue_plan(issue_objects, issue)
    by_member_component = {
        (object_plan.member_id, object_plan.component, object_plan.horizon_segment): object_plan
        for object_plan in issue_objects
    }
    short_names = gefs_reforecast_grib_short_names()
    weather_short_names = {
        component: short_names[component] for component in _WEATHER_COMPONENTS
    }
    decoded_rows = []
    for member_id in gefs_reforecast_member_ids():
        field_paths = {
            component: tuple(
                by_member_component[(member_id, component, horizon_segment)].path
                for horizon_segment in _HORIZON_SEGMENTS
            )
            for component in _WEATHER_COMPONENTS
        }
        elevation_path = by_member_component[
            (member_id, "elevation_m", _HORIZON_SEGMENTS[0])
        ].path
        decoded_rows.extend(
            decode_gefs_reforecast_grib_member(
                field_paths,
                grib_short_names=weather_short_names,
                elevation_path=elevation_path,
                elevation_short_name=short_names["elevation_m"],
                member_id=member_id,
                idaho_bbox=idaho_bbox,
                valid_dates=outlook_valid_dates(issue),
            )
        )
    return decoded_rows


def _require_exact_issue_plan(
    raw_objects: tuple[GefsReforecastRawObject, ...],
    issue_time: datetime,
) -> None:
    expected_plan = build_gefs_reforecast_acquisition_plan((issue_time,))
    expected_objects = expected_plan["objects"]
    assert isinstance(expected_objects, list)
    expected = {
        (
            object_plan["member_id"],
            object_plan["component"],
            object_plan["horizon_segment"],
            object_plan["uri"],
        )
        for object_plan in expected_objects
        if isinstance(object_plan, dict)
    }
    actual = {
        (
            object_plan.member_id,
            object_plan.component,
            object_plan.horizon_segment,
            object_plan.uri,
        )
        for object_plan in raw_objects
    }
    if len(raw_objects) != len(actual) or actual != expected:
        raise ValueError("GEFS raw issue does not match the frozen source plan")


def _require_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("GEFS issue_time must be explicit UTC")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("GEFS issue_time must be explicit UTC")
    result = value.astimezone(timezone.utc)
    if (
        result.weekday() != 2
        or result.hour != 0
        or result.minute != 0
        or result.second != 0
        or result.microsecond != 0
    ):
        raise ValueError("GEFS issue_time must be a Wednesday 00Z instant")
    return result
