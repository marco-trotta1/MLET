"""Tests for deterministic NOAA GEFSv12 reforecast object addresses."""

from __future__ import annotations

from datetime import datetime, timezone

from mlet.sources.gefs_reforecast_uri import (
    gefs_reforecast_member_ids,
    gefs_reforecast_object_uri,
)


def test_gefs_reforecast_uri_uses_the_public_v12_member_field_layout() -> None:
    """A changed path must not silently select a different NOAA product."""
    uri = gefs_reforecast_object_uri(
        datetime(2019, 7, 3, tzinfo=timezone.utc),
        member_id="c00",
        component="tmax_k",
        horizon_segment="Days:1-10",
    )

    assert uri == (
        "https://noaa-gefs-retrospective.s3.amazonaws.com/GEFSv12/reforecast/"
        "2019/2019070300/c00/Days:1-10/tmax_2m_2019070300_c00.grib2"
    )
    assert gefs_reforecast_member_ids() == (
        "c00",
        "p01",
        "p02",
        "p03",
        "p04",
        "p05",
        "p06",
        "p07",
        "p08",
        "p09",
        "p10",
    )
