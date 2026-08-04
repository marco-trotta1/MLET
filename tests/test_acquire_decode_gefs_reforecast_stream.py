"""Tests for the resumable sequential GEFS archive runner."""

from datetime import datetime, timezone

import pytest

from mlet.sources.gefs_reforecast_plan import build_gefs_reforecast_acquisition_plan
from scripts.acquire_decode_gefs_reforecast_stream import (
    build_stream_index,
    issue_plans_from_full_plan,
)


def test_full_plan_splits_into_one_canonical_plan_per_issue() -> None:
    issues = (
        datetime(2019, 7, 3, tzinfo=timezone.utc),
        datetime(2019, 7, 10, tzinfo=timezone.utc),
    )
    full = build_gefs_reforecast_acquisition_plan(issues)

    result = issue_plans_from_full_plan(full)

    assert len(result) == 2
    assert [len(plan["objects"]) for plan in result] == [187, 187]
    assert result[0]["objects"][0]["issue_time"] == "2019-07-03T00:00:00Z"


def test_full_plan_rejects_a_changed_object_url() -> None:
    full = build_gefs_reforecast_acquisition_plan(
        (datetime(2019, 7, 3, tzinfo=timezone.utc),)
    )
    objects = full["objects"]
    assert isinstance(objects, list)
    objects[0]["uri"] = "https://example.invalid/tampered"

    with pytest.raises(ValueError, match="frozen source layout"):
        issue_plans_from_full_plan(full)


def test_stream_index_orders_summaries_and_rejects_duplicates() -> None:
    summaries = [
        {"issue_time": "2019-07-10T00:00:00Z", "artifact_sha256": "b" * 64},
        {"issue_time": "2019-07-03T00:00:00Z", "artifact_sha256": "a" * 64},
    ]

    index = build_stream_index(plan_sha256="c" * 64, summaries=summaries)

    assert [item["issue_time"] for item in index["issues"]] == [
        "2019-07-03T00:00:00Z",
        "2019-07-10T00:00:00Z",
    ]
    with pytest.raises(ValueError, match="duplicate issue"):
        build_stream_index(plan_sha256="c" * 64, summaries=summaries + [summaries[0]])
