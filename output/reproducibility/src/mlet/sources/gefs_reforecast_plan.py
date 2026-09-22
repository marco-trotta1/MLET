"""Build the fixed GEFSv12 raw-object plan for an ETo hindcast."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import json
from pathlib import Path

from mlet.sources.gefs_reforecast_uri import (
    _COMPONENT_FILENAMES,
    _HORIZON_SEGMENTS,
    gefs_reforecast_member_ids,
    gefs_reforecast_object_uri,
)


def build_gefs_reforecast_acquisition_plan(
    issue_times: Sequence[datetime],
) -> dict[str, object]:
    """Return a canonical raw-file plan for the frozen weekly GEFS schedule.

    This plan identifies public objects but does not claim that they were
    retrieved. A separate retrieval receipt must provide immutable file bytes,
    checksums, and response metadata before a decoder may consume the files.
    """
    issues = tuple(issue_times)
    _validate_issue_times(issues)
    objects = []
    for issue_time in issues:
        issue_text = _format_utc(issue_time)
        timestamp = issue_time.strftime("%Y%m%d%H")
        for member_id in gefs_reforecast_member_ids():
            for horizon_segment in _HORIZON_SEGMENTS:
                local_segment = horizon_segment.replace(":", "_")
                for component in sorted(_COMPONENT_FILENAMES):
                    if component == "elevation_m" and horizon_segment != _HORIZON_SEGMENTS[0]:
                        continue
                    filename = f"{_COMPONENT_FILENAMES[component]}_{timestamp}_{member_id}.grib2"
                    objects.append(
                        {
                            "issue_time": issue_text,
                            "member_id": member_id,
                            "component": component,
                            "horizon_segment": horizon_segment,
                            "uri": gefs_reforecast_object_uri(
                                issue_time,
                                member_id=member_id,
                                component=component,
                                horizon_segment=horizon_segment,
                            ),
                            "local_path": (
                                f"raw/gefs-v12/{issue_time.year}/{timestamp}/{member_id}/"
                                f"{local_segment}/{filename}"
                            ),
                        }
                    )
    return {
        "schema_version": 1,
        "kind": "mlet.gefs.reforecast-acquisition-plan",
        "objects": objects,
    }


def write_gefs_reforecast_acquisition_plan(
    plan: dict[str, object],
    destination: Path,
) -> Path:
    """Write a new canonical acquisition plan without replacing an approved plan."""
    _validate_serialized_plan(plan)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise ValueError("GEFS acquisition plan destination must not already exist")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("GEFS acquisition plan parent must be a real directory")
    contents = (
        json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(contents)
    path.chmod(0o444)
    return path


def _validate_serialized_plan(plan: dict[str, object]) -> None:
    if not isinstance(plan, dict) or set(plan) != {"schema_version", "kind", "objects"}:
        raise ValueError("GEFS acquisition plan fields must match the schema exactly")
    objects = plan["objects"]
    if not isinstance(objects, list) or not objects:
        raise ValueError("GEFS acquisition plan objects must be a non-empty list")
    try:
        issue_times = tuple(
            sorted(
                {
                    datetime.fromisoformat(item["issue_time"].replace("Z", "+00:00"))
                    for item in objects
                    if isinstance(item, dict)
                }
            )
        )
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValueError("GEFS acquisition plan issue_time must be strict UTC text") from error
    if len(issue_times) == 0 or len(issue_times) > len(objects):
        raise ValueError("GEFS acquisition plan objects are invalid")
    if plan != build_gefs_reforecast_acquisition_plan(issue_times):
        raise ValueError("GEFS acquisition plan does not match the frozen source layout")


def _validate_issue_times(issue_times: tuple[datetime, ...]) -> None:
    if not issue_times:
        raise ValueError("GEFS acquisition plan requires at least one issue")
    if any(not isinstance(issue, datetime) for issue in issue_times):
        raise ValueError("GEFS acquisition issues must be datetimes")
    normalized = tuple(_require_weekly_wednesday_00z(issue) for issue in issue_times)
    if normalized != tuple(sorted(normalized)) or len(normalized) != len(set(normalized)):
        raise ValueError("GEFS acquisition issues must be sorted and unique")


def _require_weekly_wednesday_00z(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("GEFS acquisition issue must be explicit UTC")
    result = value.astimezone(timezone.utc)
    if (
        result.weekday() != 2
        or result.hour != 0
        or result.minute != 0
        or result.second != 0
        or result.microsecond != 0
    ):
        raise ValueError("GEFS acquisition issue must be a Wednesday 00Z instant")
    return result


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
