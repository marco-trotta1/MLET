"""Tests for local GEFSv12 GRIB decoder entry checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from mlet.sources.gefs_grib import (
    _selected_interval_hours,
    decode_gefs_reforecast_grib_member,
    gefs_reforecast_grib_short_names,
)


def test_gefs_reforecast_short_names_are_fixed_to_the_verified_v12_fields() -> None:
    """A caller must not substitute an ambiguous GRIB field name."""
    assert gefs_reforecast_grib_short_names() == {
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


def test_gefs_grib_interval_selection_infers_three_hour_point_samples() -> None:
    """Three-hour point fields must retain the interval that they represent."""
    assert _selected_interval_hours(
        "specific_humidity_kg_kg",
        step_type="instant",
        start_step=3,
        end_step=3,
    ) == (0, 3)
    assert _selected_interval_hours(
        "surface_pressure_pa",
        step_type="instant",
        start_step=6,
        end_step=6,
    ) == (3, 6)
    assert _selected_interval_hours(
        "specific_humidity_kg_kg",
        step_type="instant",
        start_step=246,
        end_step=246,
    ) == (240, 246)
    assert _selected_interval_hours(
        "shortwave_w_m2",
        step_type="avg",
        start_step=0,
        end_step=3,
    ) is None
    assert _selected_interval_hours(
        "shortwave_w_m2",
        step_type="avg",
        start_step=0,
        end_step=6,
    ) == (0, 6)
    assert _selected_interval_hours(
        "shortwave_w_m2",
        step_type="avg",
        start_step=240,
        end_step=246,
    ) == (240, 246)
    assert _selected_interval_hours(
        "tmax_k",
        step_type="max",
        start_step=0,
        end_step=6,
    ) == (0, 6)
    assert _selected_interval_hours(
        "precipitation_increment_kg_m2",
        step_type="accum",
        start_step=0,
        end_step=3,
    ) is None


def test_gefs_grib_decoder_requires_every_component_before_reading_files() -> None:
    """A partial weather driver set must not produce a daily ETo input."""
    with pytest.raises(ValueError, match="every weather component path"):
        decode_gefs_reforecast_grib_member(
            {"tmax_k": Path("missing.grib2")},
            grib_short_names={"tmax_k": "tmax"},
            elevation_path=Path("missing-height.grib2"),
            elevation_short_name="gh",
            member_id="c00",
            idaho_bbox=(-118.0, 41.0, -110.0, 50.0),
        )


def test_gefs_grib_reader_reports_a_truncated_or_invalid_file(tmp_path: Path) -> None:
    """A corrupt raw object must fail before it can create weather rows."""
    from mlet.sources.gefs_grib import read_gefs_reforecast_grid_elevation

    path = tmp_path / "truncated.grib2"
    path.write_bytes(b"GRIB")

    with pytest.raises(ValueError, match="truncated or unreadable"):
        read_gefs_reforecast_grid_elevation(
            path,
            grib_short_name="orog",
            idaho_bbox=(-118.0, 41.0, -110.0, 50.0),
        )
