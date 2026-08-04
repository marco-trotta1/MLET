"""Read selected GEFSv12 reforecast GRIB messages into component records."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from mlet.sources.gefs_reforecast import (
    aggregate_gefs_reforecast_steps,
    normalize_gefs_reforecast_daily_rows,
)

_COMPONENT_INTERVAL_SECONDS = {
    "tmax_k": 21_600,
    "tmin_k": 21_600,
    "specific_humidity_kg_kg": 10_800,
    "surface_pressure_pa": 10_800,
    "u10_m_s": 10_800,
    "v10_m_s": 10_800,
    "shortwave_w_m2": 10_800,
    "precipitation_increment_kg_m2": 21_600,
}
_COMPONENT_HEIGHT_ABOVE_GROUND_M = {
    "tmax_k": 2.0,
    "tmin_k": 2.0,
    "specific_humidity_kg_kg": 2.0,
    "surface_pressure_pa": None,
    "u10_m_s": 10.0,
    "v10_m_s": 10.0,
    "shortwave_w_m2": None,
    "precipitation_increment_kg_m2": None,
}
_GRIB_SHORT_NAMES = {
    "tmax_k": "tmax",
    "tmin_k": "tmin",
    "specific_humidity_kg_kg": "2sh",
    "surface_pressure_pa": "sp",
    "u10_m_s": "10u",
    "v10_m_s": "10v",
    "shortwave_w_m2": "sdswrf",
    "precipitation_increment_kg_m2": "tp",
    "elevation_m": "orog",
}
_POINT_SAMPLE_COMPONENTS = frozenset(
    {
        "specific_humidity_kg_kg",
        "surface_pressure_pa",
        "u10_m_s",
        "v10_m_s",
    }
)


def gefs_reforecast_grib_short_names() -> dict[str, str]:
    """Return the fixed GEFSv12 GRIB short names verified for this decoder."""
    return dict(_GRIB_SHORT_NAMES)


def read_gefs_reforecast_grib_component(
    path: Path,
    *,
    field: str,
    grib_short_name: str,
    member_id: str,
    elevation_m_by_grid: Mapping[str, float],
    idaho_bbox: tuple[float, float, float, float],
    height_above_ground_m: float | None = None,
    grid_ids: Collection[str] | None = None,
) -> list[dict[str, object]]:
    """Read one checksum-pinned GRIB component into strict interval records.

    The caller must provide the expected GRIB short name and fixed grid
    elevation. This function rejects messages with a different duration. It
    therefore excludes the interleaved six-hour products when a component
    requires three-hour values, and the converse.
    """
    try:
        import eccodes
    except ImportError as error:
        raise RuntimeError("GEFS GRIB decoding requires the mlet[gefs] extra") from error
    if field not in _COMPONENT_INTERVAL_SECONDS:
        raise ValueError("GEFS GRIB component field is unsupported")
    if not isinstance(grib_short_name, str) or not grib_short_name:
        raise ValueError("GRIB short name must be non-empty text")
    if not isinstance(member_id, str) or not member_id:
        raise ValueError("GEFS member_id must be non-empty text")
    west, south, east, north = _validate_bbox(idaho_bbox)
    if not elevation_m_by_grid:
        raise ValueError("GEFS GRIB decoder requires fixed grid elevations")

    component: list[dict[str, object]] = []
    with Path(path).open("rb") as handle:
        while message := _next_grib_message(handle, eccodes):
            try:
                if eccodes.codes_get(message, "shortName") != grib_short_name:
                    continue
                if height_above_ground_m is not None and not _has_height_above_ground(
                    message, eccodes, height_above_ground_m
                ):
                    continue
                interval = _selected_interval_hours(
                    field,
                    step_type=str(eccodes.codes_get(message, "stepType")),
                    start_step=int(eccodes.codes_get(message, "startStep")),
                    end_step=int(eccodes.codes_get(message, "endStep")),
                )
                if interval is None:
                    continue
                start_step, end_step = interval
                issue_time = _issue_time(message, eccodes)
                canonical_intervals = (
                    ((start_step, start_step + 3), (start_step + 3, end_step))
                    if (
                        field == "shortwave_w_m2" or field in _POINT_SAMPLE_COMPONENTS
                    )
                    and end_step - start_step == 6
                    else ((start_step, end_step),)
                )
                for latitude, longitude, value in _idaho_values(
                    message, eccodes, west, south, east, north
                ):
                    grid_id = f"{latitude:.2f}:{longitude:.2f}"
                    if grid_ids is not None and grid_id not in grid_ids:
                        continue
                    try:
                        elevation_m = elevation_m_by_grid[grid_id]
                    except KeyError as error:
                        raise ValueError(
                            "GEFS GRIB decoder is missing an elevation for its grid cell"
                        ) from error
                    for canonical_start_step, canonical_end_step in canonical_intervals:
                        interval_start = issue_time + timedelta(hours=canonical_start_step)
                        interval_end = issue_time + timedelta(hours=canonical_end_step)
                        component.append(
                            {
                                "field": field,
                                "grid_id": grid_id,
                                "latitude": latitude,
                                "longitude": longitude,
                                "elevation_m": elevation_m,
                                "member_id": member_id,
                                "interval_start_at": _format_utc(interval_start),
                                "interval_end_at": _format_utc(interval_end),
                                "value": value,
                            }
                        )
            finally:
                eccodes.codes_release(message)
    if not component:
        raise ValueError("GEFS GRIB component contains no selected Idaho messages")
    return component


def read_gefs_reforecast_grid_elevation(
    path: Path,
    *,
    grib_short_name: str,
    idaho_bbox: tuple[float, float, float, float],
) -> dict[str, float]:
    """Read one fixed GEFS surface-height field for the selected grid cells."""
    try:
        import eccodes
    except ImportError as error:
        raise RuntimeError("GEFS GRIB decoding requires the mlet[gefs] extra") from error
    west, south, east, north = _validate_bbox(idaho_bbox)
    elevations: dict[str, float] = {}
    with Path(path).open("rb") as handle:
        while message := _next_grib_message(handle, eccodes):
            try:
                if eccodes.codes_get(message, "shortName") != grib_short_name:
                    continue
                for latitude, longitude, elevation_m in _idaho_values(
                    message, eccodes, west, south, east, north
                ):
                    grid_id = f"{latitude:.2f}:{longitude:.2f}"
                    previous = elevations.setdefault(grid_id, elevation_m)
                    if previous != elevation_m:
                        raise ValueError("GEFS surface height changed between messages")
            finally:
                eccodes.codes_release(message)
    if not elevations:
        raise ValueError("GEFS elevation GRIB file contains no Idaho surface heights")
    return elevations


def decode_gefs_reforecast_grib_member(
    field_paths: Mapping[str, tuple[Path, ...]],
    *,
    grib_short_names: Mapping[str, str],
    elevation_path: Path,
    elevation_short_name: str,
    member_id: str,
    idaho_bbox: tuple[float, float, float, float],
    valid_dates: Collection[date] | None = None,
) -> list[dict[str, object]]:
    """Decode all required GRIB fields for one member to canonical daily rows."""
    if set(field_paths) != set(_COMPONENT_INTERVAL_SECONDS):
        raise ValueError("GEFS GRIB decoder requires every weather component path")
    if any(
        not isinstance(paths, tuple) or not paths or any(not isinstance(path, Path) for path in paths)
        for paths in field_paths.values()
    ):
        raise ValueError("GEFS GRIB decoder component paths must be non-empty Path tuples")
    if set(grib_short_names) != set(_COMPONENT_INTERVAL_SECONDS):
        raise ValueError("GEFS GRIB decoder requires every component short name")
    elevations = read_gefs_reforecast_grid_elevation(
        elevation_path,
        grib_short_name=elevation_short_name,
        idaho_bbox=idaho_bbox,
    )
    long_range_shortwave = read_gefs_reforecast_grib_component(
        field_paths["shortwave_w_m2"][-1],
        field="shortwave_w_m2",
        grib_short_name=grib_short_names["shortwave_w_m2"],
        member_id=member_id,
        elevation_m_by_grid=elevations,
        idaho_bbox=idaho_bbox,
        height_above_ground_m=_COMPONENT_HEIGHT_ABOVE_GROUND_M["shortwave_w_m2"],
    )
    common_grid_ids = frozenset(
        str(row["grid_id"]) for row in long_range_shortwave
    )
    steps = []
    for field in sorted(field_paths):
        for path in field_paths[field]:
            steps.extend(
                read_gefs_reforecast_grib_component(
                    path,
                    field=field,
                    grib_short_name=grib_short_names[field],
                    member_id=member_id,
                    elevation_m_by_grid=elevations,
                    idaho_bbox=idaho_bbox,
                    height_above_ground_m=_COMPONENT_HEIGHT_ABOVE_GROUND_M[field],
                    grid_ids=common_grid_ids,
                )
            )
    return normalize_gefs_reforecast_daily_rows(
        aggregate_gefs_reforecast_steps(steps, valid_dates=valid_dates)
    )


def _next_grib_message(handle: object, eccodes: object) -> object:
    """Read one GRIB message and normalize decoder-specific read failures."""
    try:
        return eccodes.codes_grib_new_from_file(handle)
    except Exception as error:
        raise ValueError("GEFS GRIB file is truncated or unreadable") from error


def _selected_interval_hours(
    field: str,
    *,
    step_type: str,
    start_step: int,
    end_step: int,
) -> Optional[tuple[int, int]]:
    """Return the source interval used by one selected GRIB message."""
    try:
        expected_hours = _COMPONENT_INTERVAL_SECONDS[field] // 3600
    except KeyError as error:
        raise ValueError("GEFS GRIB component field is unsupported") from error
    if field == "shortwave_w_m2":
        if step_type == "avg" and end_step - start_step == expected_hours * 2:
            return start_step, end_step
        return None
    if end_step - start_step == expected_hours:
        return start_step, end_step
    if (
        field in _POINT_SAMPLE_COMPONENTS
        and step_type == "instant"
        and start_step == end_step
        and end_step >= expected_hours
    ):
        interval_hours = 6 if end_step >= 246 else expected_hours
        return end_step - interval_hours, end_step
    return None


def _idaho_values(
    message: object,
    eccodes: object,
    west: float,
    south: float,
    east: float,
    north: float,
) -> list[tuple[float, float, float]]:
    """Return Idaho cells from one regular latitude-longitude GRIB message."""
    assert hasattr(eccodes, "codes_get")
    if eccodes.codes_get(message, "gridType") != "regular_ll":
        raise ValueError("GEFS GRIB decoder requires a regular latitude-longitude grid")
    latitude_count = int(eccodes.codes_get(message, "Nj"))
    longitude_count = int(eccodes.codes_get(message, "Ni"))
    first_latitude = float(eccodes.codes_get(message, "latitudeOfFirstGridPointInDegrees"))
    first_longitude = float(eccodes.codes_get(message, "longitudeOfFirstGridPointInDegrees"))
    latitude_increment = float(eccodes.codes_get(message, "jDirectionIncrementInDegrees"))
    longitude_increment = float(eccodes.codes_get(message, "iDirectionIncrementInDegrees"))
    values = eccodes.codes_get_values(message)
    if len(values) != latitude_count * longitude_count:
        raise ValueError("GEFS GRIB grid dimensions do not match message values")
    selected = []
    for latitude_index in range(latitude_count):
        latitude = first_latitude - latitude_index * latitude_increment
        if not south <= latitude <= north:
            continue
        for longitude_index in range(longitude_count):
            longitude_360 = first_longitude + longitude_index * longitude_increment
            longitude = longitude_360 - 360.0 if longitude_360 > 180.0 else longitude_360
            if west <= longitude <= east:
                value = float(values[latitude_index * longitude_count + longitude_index])
                selected.append((latitude, longitude, value))
    return selected


def _issue_time(message: object, eccodes: object) -> datetime:
    data_date = int(eccodes.codes_get(message, "dataDate"))
    data_time = int(eccodes.codes_get(message, "dataTime"))
    return datetime.strptime(
        f"{data_date:08d}{data_time:04d}", "%Y%m%d%H%M"
    ).replace(tzinfo=timezone.utc)


def _has_height_above_ground(
    message: object, eccodes: object, expected_height_m: float
) -> bool:
    return (
        eccodes.codes_get(message, "typeOfLevel") == "heightAboveGround"
        and float(eccodes.codes_get(message, "level")) == expected_height_m
    )


def _validate_bbox(value: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if not isinstance(value, tuple) or len(value) != 4:
        raise ValueError("GEFS GRIB bbox must be a four-value tuple")
    west, south, east, north = value
    if not all(type(item) in (int, float) for item in value):
        raise ValueError("GEFS GRIB bbox values must be finite numbers")
    if not -180.0 <= west < east <= 180.0 or not -90.0 <= south < north <= 90.0:
        raise ValueError("GEFS GRIB bbox is invalid")
    return float(west), float(south), float(east), float(north)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
