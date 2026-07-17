import dataclasses
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from mlet.outlook.contracts import (
    OutlookDay,
    OutlookQuantiles,
    SourceRecord,
    WeatherMember,
)
from mlet.outlook.manifest import RunManifest, build_manifest


def test_identical_inputs_produce_identical_run_id(tmp_path: Path) -> None:
    source = tmp_path / "weather.jsonl"
    source.write_text('{"fixture": true, "non_scientific": true}\n')

    first = build_manifest(
        "2026-07-16T00:00:00Z",
        {"weather": source},
        "abc123",
        "2026-07-16T00:05:00Z",
    )
    second = build_manifest(
        "2026-07-16T00:00:00Z",
        {"weather": source},
        "abc123",
        "2026-07-16T00:05:00Z",
    )

    assert first.run_id == second.run_id
    assert first.sources[0].sha256 == second.sources[0].sha256


def test_changed_source_bytes_change_sha256_and_run_id(tmp_path: Path) -> None:
    source = tmp_path / "weather.jsonl"
    source.write_text('{"fixture": true, "non_scientific": true}\n')
    first = build_manifest(
        "2026-07-16T00:00:00Z",
        {"weather": source},
        "abc123",
        "2026-07-16T00:05:00Z",
    )

    source.write_text('{"fixture": "changed", "non_scientific": true}\n')
    second = build_manifest(
        "2026-07-16T00:00:00Z",
        {"weather": source},
        "abc123",
        "2026-07-16T00:05:00Z",
    )

    assert first.sources[0].sha256 != second.sources[0].sha256
    assert first.run_id != second.run_id


def test_manifest_round_trip_preserves_explicit_utc_timestamps(tmp_path: Path) -> None:
    source = tmp_path / "weather.jsonl"
    source.write_text('{"fixture": true, "non_scientific": true}\n')
    manifest = build_manifest(
        "2026-07-16T00:00:00Z",
        {"weather": source},
        "abc123",
        "2026-07-16T00:05:00Z",
    )

    restored = RunManifest.from_json(manifest.to_json())

    assert restored == manifest
    assert '"issued_at":"2026-07-16T00:00:00Z"' in manifest.to_json()
    assert '"retrieved_at":"2026-07-16T00:05:00Z"' in manifest.to_json()


@pytest.mark.parametrize(
    "timestamp",
    ["2026-07-16T00:00:00", "2026-07-16T00:00:00+00:00"],
)
def test_manifest_requires_explicit_zulu_utc_timestamps(
    tmp_path: Path, timestamp: str
) -> None:
    source = tmp_path / "weather.jsonl"
    source.write_text('{"fixture": true, "non_scientific": true}\n')

    with pytest.raises(ValueError, match="UTC ISO-8601"):
        build_manifest(timestamp, {"weather": source}, "abc123", timestamp)


def test_outlook_contracts_have_the_frozen_public_fields() -> None:
    assert [field.name for field in dataclasses.fields(WeatherMember)] == [
        "grid_id",
        "latitude",
        "longitude",
        "elevation_m",
        "member_id",
        "issued_at",
        "valid_date",
        "tmax_c",
        "tmin_c",
        "vapor_pressure_kpa",
        "wind_m_s",
        "solar_mj_m2_day",
        "precip_mm",
    ]
    assert [field.name for field in dataclasses.fields(SourceRecord)] == [
        "name",
        "uri",
        "retrieved_at",
        "sha256",
        "observed_through",
    ]
    assert [field.name for field in dataclasses.fields(OutlookQuantiles)] == [
        "p10",
        "p50",
        "p90",
    ]
    assert [field.name for field in dataclasses.fields(OutlookDay)] == [
        "grid_id",
        "valid_date",
        "eto_mm",
        "potential_et_c_mm",
        "eta_well_watered_mm",
        "eta_no_irrigation_mm",
        "eta_analysis_mm",
        "eta_analysis_date",
    ]

    issued_at = datetime(2026, 7, 16, tzinfo=timezone.utc)
    member = WeatherMember(
        "idaho-001",
        43.6,
        -116.2,
        824.0,
        "member-01",
        issued_at,
        date(2026, 7, 16),
        30.0,
        14.0,
        1.5,
        2.0,
        25.0,
        0.0,
    )
    assert dataclasses.is_dataclass(member)
    with pytest.raises(dataclasses.FrozenInstanceError):
        member.grid_id = "changed"  # type: ignore[misc]


def test_vendored_pyfao56_reference_et_import_surface_is_available() -> None:
    from pyfao56 import refet

    assert refet.ascedaily.__name__ == "ascedaily"
