"""Tests for the deterministic GEFSv12 raw-acquisition plan."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from mlet.sources.gefs_reforecast_plan import (
    build_gefs_reforecast_acquisition_plan,
    write_gefs_reforecast_acquisition_plan,
)


def test_acquisition_plan_expands_one_weekly_issue_to_every_required_object() -> None:
    """The raw file set must be fixed before data retrieval starts."""
    plan = build_gefs_reforecast_acquisition_plan(
        (datetime(2019, 7, 3, tzinfo=timezone.utc),)
    )

    assert plan["kind"] == "mlet.gefs.reforecast-acquisition-plan"
    assert plan["schema_version"] == 1
    assert len(plan["objects"]) == 187
    assert sum(item["component"] == "elevation_m" for item in plan["objects"]) == 11
    assert plan["objects"][0] == {
        "component": "elevation_m",
        "horizon_segment": "Days:1-10",
        "issue_time": "2019-07-03T00:00:00Z",
        "local_path": (
            "raw/gefs-v12/2019/2019070300/c00/Days_1-10/"
            "hgt_sfc_2019070300_c00.grib2"
        ),
        "member_id": "c00",
        "uri": (
            "https://noaa-gefs-retrospective.s3.amazonaws.com/GEFSv12/reforecast/"
            "2019/2019070300/c00/Days:1-10/hgt_sfc_2019070300_c00.grib2"
        ),
    }


def test_acquisition_plan_rejects_unsorted_or_non_00z_issue_times() -> None:
    """Ambiguous schedules cannot be turned into a source plan."""
    issue = datetime(2019, 7, 3, tzinfo=timezone.utc)

    try:
        build_gefs_reforecast_acquisition_plan((issue, issue))
    except ValueError as error:
        assert "sorted and unique" in str(error)
    else:
        raise AssertionError("duplicate issue must be rejected")


def test_acquisition_plan_rejects_non_wednesday_issue_times() -> None:
    """A daily five-member issue must not enter the weekly ensemble plan."""
    try:
        build_gefs_reforecast_acquisition_plan(
            (datetime(2019, 7, 1, tzinfo=timezone.utc),)
        )
    except ValueError as error:
        assert "Wednesday" in str(error)
    else:
        raise AssertionError("non-weekly issue must be rejected")


def test_acquisition_plan_writes_canonical_new_bytes(tmp_path: Path) -> None:
    """An approved plan cannot be replaced during a source retrieval."""
    plan = build_gefs_reforecast_acquisition_plan(
        (datetime(2019, 7, 3, tzinfo=timezone.utc),)
    )

    path = write_gefs_reforecast_acquisition_plan(plan, tmp_path / "plan.json")

    assert json.loads(path.read_text(encoding="utf-8")) == plan
