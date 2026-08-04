"""Tests for the immutable historical GEFS reforecast catalog."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mlet.sources.gefs_archive import load_gefs_reforecast_catalog


def test_gefs_reforecast_catalog_binds_each_issue_to_immutable_raw_and_daily_bytes(
    tmp_path: Path,
) -> None:
    """Removing a raw checksum must fail the historical replay contract."""
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "mlet.gefs.reforecast-catalog",
                "issues": [
                    {
                        "issue_time": "2019-07-01T00:00:00Z",
                        "raw_uri": "s3://noaa-gefs-retrospective/20190701/gefs.grib2",
                        "raw_sha256": "a" * 64,
                        "daily_artifact_uri": "file:///archive/gefs-20190701.json",
                        "daily_artifact_sha256": "b" * 64,
                        "transform_version": "1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    catalog = load_gefs_reforecast_catalog(path)

    assert catalog[0].issue_time.isoformat() == "2019-07-01T00:00:00+00:00"
    assert catalog[0].raw_sha256 == "a" * 64


def test_gefs_reforecast_catalog_rejects_duplicate_issue_times(tmp_path: Path) -> None:
    """Two sources for one issue must not make historical replay ambiguous."""
    issue = {
        "issue_time": "2019-07-01T00:00:00Z",
        "raw_uri": "s3://noaa-gefs-retrospective/20190701/gefs.grib2",
        "raw_sha256": "a" * 64,
        "daily_artifact_uri": "file:///archive/gefs-20190701.json",
        "daily_artifact_sha256": "b" * 64,
        "transform_version": "1",
    }
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "mlet.gefs.reforecast-catalog",
                "issues": [issue, issue],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_gefs_reforecast_catalog(path)
