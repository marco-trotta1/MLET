"""Construct fixed public GEFSv12 reforecast object URIs."""

from __future__ import annotations

from datetime import datetime, timezone


_BASE_URI = "https://noaa-gefs-retrospective.s3.amazonaws.com/GEFSv12/reforecast"
_COMPONENT_FILENAMES = {
    "tmax_k": "tmax_2m",
    "tmin_k": "tmin_2m",
    "specific_humidity_kg_kg": "spfh_2m",
    "surface_pressure_pa": "pres_sfc",
    "u10_m_s": "ugrd_hgt",
    "v10_m_s": "vgrd_hgt",
    "shortwave_w_m2": "dswrf_sfc",
    "precipitation_increment_kg_m2": "apcp_sfc",
    "elevation_m": "hgt_sfc",
}
_HORIZON_SEGMENTS = ("Days:1-10", "Days:10-35")
_MEMBER_IDS = ("c00", *(f"p{index:02d}" for index in range(1, 11)))


def gefs_reforecast_member_ids() -> tuple[str, ...]:
    """Return the frozen weekly 11-member GEFSv12 reforecast ensemble."""
    return _MEMBER_IDS


def gefs_reforecast_object_uri(
    issue_time: datetime,
    *,
    member_id: str,
    component: str,
    horizon_segment: str,
) -> str:
    """Return one exact public GRIB object address for a frozen issue input."""
    if not isinstance(issue_time, datetime) or issue_time.tzinfo is None:
        raise ValueError("GEFS issue_time must be explicit UTC")
    if issue_time.utcoffset() != timezone.utc.utcoffset(issue_time):
        raise ValueError("GEFS issue_time must be explicit UTC")
    issue = issue_time.astimezone(timezone.utc)
    if issue.hour != 0 or issue.minute != 0 or issue.second != 0 or issue.microsecond != 0:
        raise ValueError("GEFS reforecast issue_time must be 00Z")
    if member_id not in _MEMBER_IDS:
        raise ValueError("GEFS reforecast member_id is unsupported")
    try:
        filename_prefix = _COMPONENT_FILENAMES[component]
    except KeyError as error:
        raise ValueError("GEFS reforecast component is unsupported") from error
    if horizon_segment not in _HORIZON_SEGMENTS:
        raise ValueError("GEFS reforecast horizon segment is unsupported")
    timestamp = issue.strftime("%Y%m%d%H")
    return (
        f"{_BASE_URI}/{issue.year}/{timestamp}/{member_id}/{horizon_segment}/"
        f"{filename_prefix}_{timestamp}_{member_id}.grib2"
    )
