"""Tests for GEFSv12 reforecast unit conversion before artifact import."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from mlet.sources.gefs_reforecast import (
    aggregate_gefs_reforecast_steps,
    normalize_gefs_reforecast_daily_rows,
)


def test_gefs_reforecast_normalizer_converts_grib_units_to_asce_inputs() -> None:
    """Changing Kelvin, radiation, or humidity conversion must fail this contract."""
    rows = normalize_gefs_reforecast_daily_rows(
        [
            {
                "grid_id": "43:-117",
                "latitude": 43.5,
                "longitude": -116.5,
                "elevation_m": 824.0,
                "member_id": "c00",
                "valid_date": "2019-07-02",
                "tmax_k": 303.15,
                "tmin_k": 285.15,
                "specific_humidity_kg_kg": 0.01,
                "surface_pressure_pa": 100000.0,
                "u10_m_s": 3.0,
                "v10_m_s": 4.0,
                "shortwave_j_m2_day": 25000000.0,
                "precipitation_kg_m2_day": 2.5,
            }
        ]
    )

    assert rows[0]["tmax_c"] == pytest.approx(30.0)
    assert rows[0]["tmin_c"] == pytest.approx(12.0)
    assert rows[0]["wind_m_s"] == pytest.approx(5.0)
    assert rows[0]["solar_mj_m2_day"] == pytest.approx(25.0)
    assert rows[0]["precip_mm"] == pytest.approx(2.5)
    assert rows[0]["vapor_pressure_kpa"] == pytest.approx(1.598006, rel=1e-6)


def test_gefs_reforecast_aggregator_filters_steps_outside_requested_dates() -> None:
    """A partial lead-0 local day must not reach daily completeness checks."""
    step = {
        "field": "shortwave_w_m2",
        "grid_id": "43:-117",
        "latitude": 43.5,
        "longitude": -116.5,
        "elevation_m": 824.0,
        "member_id": "c00",
        "interval_start_at": "2019-07-02T06:00:00Z",
        "interval_end_at": "2019-07-02T09:00:00Z",
        "value": 100.0,
    }

    assert aggregate_gefs_reforecast_steps(
        [step], valid_dates=(date(2019, 7, 3),)
    ) == []


def test_gefs_reforecast_aggregator_assigns_three_hour_intervals_by_boise_midpoint() -> None:
    """Midnight-ending intervals must remain in the Idaho day they describe."""
    first_end = datetime(2019, 7, 2, 9, tzinfo=timezone.utc)
    three_hour_steps = [
        {
            "field": field,
            "grid_id": "43:-117",
            "latitude": 43.5,
            "longitude": -116.5,
            "elevation_m": 824.0,
            "member_id": "c00",
            "interval_start_at": (
                first_end + timedelta(hours=3 * index - 3)
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval_end_at": (first_end + timedelta(hours=3 * index)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "value": value,
        }
        for field, value in (
            ("specific_humidity_kg_kg", 0.01),
            ("surface_pressure_pa", 100000.0),
            ("u10_m_s", 3.0),
            ("v10_m_s", 4.0),
            ("shortwave_w_m2", 100.0),
        )
        for index in range(8)
    ]
    first_six_hour_end = datetime(2019, 7, 2, 12, tzinfo=timezone.utc)
    six_hour_steps = [
        {
            "field": field,
            "grid_id": "43:-117",
            "latitude": 43.5,
            "longitude": -116.5,
            "elevation_m": 824.0,
            "member_id": "c00",
            "interval_start_at": (
                first_six_hour_end + timedelta(hours=6 * index - 6)
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval_end_at": (
                first_six_hour_end + timedelta(hours=6 * index)
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "value": value + index * change,
        }
        for field, value, change in (
            ("tmax_k", 300.0, 1.0),
            ("tmin_k", 280.0, -1.0),
            ("precipitation_increment_kg_m2", 0.5, 0.0),
        )
        for index in range(4)
    ]

    daily = aggregate_gefs_reforecast_steps(three_hour_steps + six_hour_steps)
    normalized = normalize_gefs_reforecast_daily_rows(daily)

    assert daily[0]["valid_date"] == "2019-07-02"
    assert daily[0]["tmax_k"] == pytest.approx(303.0)
    assert daily[0]["tmin_k"] == pytest.approx(277.0)
    assert daily[0]["shortwave_j_m2_day"] == pytest.approx(8640000.0)
    assert daily[0]["precipitation_kg_m2_day"] == pytest.approx(2.0)
    assert normalized[0]["wind_m_s"] == pytest.approx(5.0)


def test_gefs_reforecast_aggregator_keeps_eight_intervals_on_dst_transition() -> None:
    """The fixed forecast-bin rule must not lose the spring-forward day."""
    first_end = datetime(2019, 3, 10, 9, tzinfo=timezone.utc)
    three_hour_steps = [
        {
            "field": field,
            "grid_id": "43:-117",
            "latitude": 43.5,
            "longitude": -116.5,
            "elevation_m": 824.0,
            "member_id": "c00",
            "interval_start_at": (
                first_end + timedelta(hours=3 * index - 3)
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval_end_at": (first_end + timedelta(hours=3 * index)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "value": value,
        }
        for field, value in (
            ("specific_humidity_kg_kg", 0.01),
            ("surface_pressure_pa", 100000.0),
            ("u10_m_s", 3.0),
            ("v10_m_s", 4.0),
            ("shortwave_w_m2", 100.0),
        )
        for index in range(8)
    ]
    first_six_hour_end = datetime(2019, 3, 10, 12, tzinfo=timezone.utc)
    six_hour_steps = [
        {
            "field": field,
            "grid_id": "43:-117",
            "latitude": 43.5,
            "longitude": -116.5,
            "elevation_m": 824.0,
            "member_id": "c00",
            "interval_start_at": (
                first_six_hour_end + timedelta(hours=6 * index - 6)
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval_end_at": (
                first_six_hour_end + timedelta(hours=6 * index)
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "value": value,
        }
        for field, value in (
            ("tmax_k", 300.0),
            ("tmin_k", 280.0),
            ("precipitation_increment_kg_m2", 0.0),
        )
        for index in range(4)
    ]

    daily = aggregate_gefs_reforecast_steps(three_hour_steps + six_hour_steps)

    assert [row["valid_date"] for row in daily] == ["2019-03-10"]
