"""Tests for the checked public GEFS decoder feasibility objects."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from mlet.sources.gefs_grib import gefs_reforecast_grib_short_names
from mlet.sources.gefs_reforecast_uri import gefs_reforecast_object_uri


def test_decoder_feasibility_manifest_binds_verified_public_objects() -> None:
    """A changed URI or short name must invalidate the source feasibility record."""
    path = Path("data/outlook/gefs_reforecast_decoder_feasibility.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["classification"] == "software_source_feasibility_not_hindcast_evidence"
    assert payload["issue_time"] == "2019-07-01T00:00:00Z"
    short_names = gefs_reforecast_grib_short_names()
    for object_record in payload["objects"]:
        assert object_record["uri"] == gefs_reforecast_object_uri(
            datetime(2019, 7, 1, tzinfo=timezone.utc),
            member_id="c00",
            component=object_record["component"],
            horizon_segment="Days:1-10",
        )
        assert object_record["grib_short_name"] == short_names[object_record["component"]]
        assert len(object_record["sha256"]) == 64
        assert object_record["byte_count"] > 0
