import dataclasses
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from mlet.outlook.contracts import (
    OutlookDay,
    OutlookQuantiles,
    SourceRecord,
    WeatherMember,
)
from mlet.outlook.manifest import (
    RunManifest,
    _normalize_zulu_timestamp,
    build_manifest,
)


def _manifest_json_with_valid_run_id(payload: dict[str, object]) -> str:
    """Serialize a deliberately modified payload with its matching digest."""
    identity_payload = dict(payload)
    identity_payload.pop("run_id")
    payload["run_id"] = hashlib.sha256(
        json.dumps(
            identity_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()[:16]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _two_source_manifest(tmp_path: Path) -> RunManifest:
    alpha = tmp_path / "alpha.jsonl"
    zulu = tmp_path / "zulu.jsonl"
    alpha.write_text('{"fixture": "alpha", "non_scientific": true}\n')
    zulu.write_text('{"fixture": "zulu", "non_scientific": true}\n')
    return build_manifest(
        "2026-07-16T00:00:00Z",
        {"zulu": zulu, "alpha": alpha},
        "abc123",
        "2026-07-16T00:05:00Z",
    )


def test_zulu_timestamp_is_normalized_before_datetime_parsing() -> None:
    assert (
        _normalize_zulu_timestamp("2026-07-16T00:00:00Z")
        == "2026-07-16T00:00:00+00:00"
    )


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
    [
        "2026-07-16 00:00:00Z",
        "2026-07-16X00:00:00Z",
        "2026-07-16T00:00:00,1Z",
        "2026-07-16T00:00:00.1Z",
        "2026-07-16T00:00:00.1234567Z",
    ],
)
def test_build_manifest_rejects_noncanonical_utc_timestamp_grammar(
    tmp_path: Path, timestamp: str
) -> None:
    source = tmp_path / "weather.jsonl"
    source.write_text('{"fixture": true, "non_scientific": true}\n')

    with pytest.raises(ValueError, match="UTC ISO-8601"):
        build_manifest(timestamp, {"weather": source}, "abc123", timestamp)


def test_manifest_from_json_rejects_noncanonical_utc_timestamp_grammar(
    tmp_path: Path,
) -> None:
    manifest = _two_source_manifest(tmp_path)
    payload = json.loads(manifest.to_json())
    payload["issued_at"] = "2026-07-16X00:00:00Z"

    with pytest.raises(ValueError, match="run receipt schema"):
        RunManifest.from_json(_manifest_json_with_valid_run_id(payload))


def test_manifest_from_json_rejects_duplicate_known_top_level_key(tmp_path: Path) -> None:
    manifest = _two_source_manifest(tmp_path)
    duplicate_schema_version = manifest.to_json().replace(
        '"schema_version":1', '"schema_version":1,"schema_version":1'
    )

    with pytest.raises(ValueError, match="duplicate"):
        RunManifest.from_json(duplicate_schema_version)


def test_manifest_rejects_unknown_top_level_json_field(tmp_path: Path) -> None:
    manifest = _two_source_manifest(tmp_path)
    payload = json.loads(manifest.to_json())
    payload["unexpected"] = "not part of the manifest schema"

    with pytest.raises(ValueError, match="schema"):
        RunManifest.from_json(_manifest_json_with_valid_run_id(payload))


def test_manifest_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    manifest = _two_source_manifest(tmp_path)
    payload = json.loads(manifest.to_json())
    payload["schema_version"] = 99

    with pytest.raises(ValueError, match="schema"):
        RunManifest.from_json(_manifest_json_with_valid_run_id(payload))


def test_manifest_to_json_rejects_directly_constructed_unsupported_schema_version(
    tmp_path: Path,
) -> None:
    manifest = _two_source_manifest(tmp_path)
    provisional = RunManifest(
        schema_version=99,
        run_id="",
        issued_at=manifest.issued_at,
        retrieved_at=manifest.retrieved_at,
        git_revision=manifest.git_revision,
        sources=manifest.sources,
    )
    unsupported_manifest = dataclasses.replace(
        provisional,
        run_id=hashlib.sha256(
            json.dumps(
                provisional._payload_without_run_id(),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()[:16],
    )

    with pytest.raises(ValueError, match="schema_version is not supported"):
        unsupported_manifest.to_json()


def test_manifest_to_json_round_trips_valid_direct_construction(tmp_path: Path) -> None:
    manifest = _two_source_manifest(tmp_path)
    direct_manifest = RunManifest(
        schema_version=manifest.schema_version,
        run_id=manifest.run_id,
        issued_at=manifest.issued_at,
        retrieved_at=manifest.retrieved_at,
        git_revision=manifest.git_revision,
        sources=manifest.sources,
    )

    assert RunManifest.from_json(direct_manifest.to_json()) == direct_manifest


def test_manifest_rejects_missing_identity_source_field(tmp_path: Path) -> None:
    manifest = _two_source_manifest(tmp_path)
    payload = json.loads(manifest.to_json())
    source_payloads = payload["sources"]
    assert isinstance(source_payloads, list)
    source_payloads[0].pop("observed_through")

    with pytest.raises(ValueError, match="schema"):
        RunManifest.from_json(_manifest_json_with_valid_run_id(payload))


def test_manifest_sorts_source_names_deterministically(tmp_path: Path) -> None:
    manifest = _two_source_manifest(tmp_path)

    assert [source.name for source in manifest.sources] == ["alpha", "zulu"]


def test_manifest_rejects_unsorted_serialized_sources(tmp_path: Path) -> None:
    manifest = _two_source_manifest(tmp_path)
    payload = json.loads(manifest.to_json())
    source_payloads = payload["sources"]
    assert isinstance(source_payloads, list)
    payload["sources"] = list(reversed(source_payloads))

    with pytest.raises(ValueError, match="strictly sorted"):
        RunManifest.from_json(_manifest_json_with_valid_run_id(payload))


def test_manifest_rejects_duplicate_serialized_sources(tmp_path: Path) -> None:
    manifest = _two_source_manifest(tmp_path)
    payload = json.loads(manifest.to_json())
    source_payloads = payload["sources"]
    assert isinstance(source_payloads, list)
    payload["sources"] = [source_payloads[0], source_payloads[0]]

    with pytest.raises(ValueError, match="strictly sorted"):
        RunManifest.from_json(_manifest_json_with_valid_run_id(payload))


def test_manifest_to_json_rejects_directly_constructed_unsorted_sources(
    tmp_path: Path,
) -> None:
    manifest = _two_source_manifest(tmp_path)
    unsorted_manifest = RunManifest(
        schema_version=manifest.schema_version,
        run_id=manifest.run_id,
        issued_at=manifest.issued_at,
        retrieved_at=manifest.retrieved_at,
        git_revision=manifest.git_revision,
        sources=tuple(reversed(manifest.sources)),
    )

    with pytest.raises(ValueError, match="strictly sorted"):
        unsorted_manifest.to_json()


def test_manifest_to_json_rejects_directly_constructed_duplicate_sources(
    tmp_path: Path,
) -> None:
    manifest = _two_source_manifest(tmp_path)
    duplicate_manifest = RunManifest(
        schema_version=manifest.schema_version,
        run_id=manifest.run_id,
        issued_at=manifest.issued_at,
        retrieved_at=manifest.retrieved_at,
        git_revision=manifest.git_revision,
        sources=(manifest.sources[0], manifest.sources[0]),
    )

    with pytest.raises(ValueError, match="strictly sorted"):
        duplicate_manifest.to_json()


def test_manifest_to_json_rejects_directly_constructed_stale_run_id(
    tmp_path: Path,
) -> None:
    manifest = _two_source_manifest(tmp_path)
    stale_manifest = RunManifest(
        schema_version=manifest.schema_version,
        run_id="stale-run-id",
        issued_at=manifest.issued_at,
        retrieved_at=manifest.retrieved_at,
        git_revision=manifest.git_revision,
        sources=manifest.sources,
    )

    with pytest.raises(ValueError, match="run_id does not match"):
        stale_manifest.to_json()


def test_manifest_from_json_rejects_noncanonical_observed_through_date(
    tmp_path: Path,
) -> None:
    manifest = _two_source_manifest(tmp_path)
    payload = json.loads(manifest.to_json())
    source_payloads = payload["sources"]
    assert isinstance(source_payloads, list)
    source_payloads[0]["observed_through"] = "20260715"

    with pytest.raises(ValueError, match="run receipt schema"):
        RunManifest.from_json(_manifest_json_with_valid_run_id(payload))


def test_manifest_from_json_round_trips_canonical_observed_through_bytes(
    tmp_path: Path,
) -> None:
    manifest = _two_source_manifest(tmp_path)
    payload = json.loads(manifest.to_json())
    source_payloads = payload["sources"]
    assert isinstance(source_payloads, list)
    source_payloads[0]["observed_through"] = "2026-07-15"
    canonical_json = _manifest_json_with_valid_run_id(payload)

    assert RunManifest.from_json(canonical_json).to_json() == canonical_json


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
