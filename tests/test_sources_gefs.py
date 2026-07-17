"""Software-only tests for the imported GEFS daily-artifact boundary."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import socket

import pytest

from mlet.sources.gefs import (
    fetch_gefs,
    materialize_gefs_daily_artifact,
    normalize_gefs_rows,
)


ISSUED_AT = "2026-07-16T00:00:00Z"
IDAHO_BBOX = (-117.25, 42.0, -111.0, 49.0)
VARIABLES = [
    "precip_mm",
    "solar_mj_m2_day",
    "tmax_c",
    "tmin_c",
    "vapor_pressure_kpa",
    "wind_m_s",
]


def _gefs_rows() -> list[dict[str, object]]:
    """Return synthetic, non-scientific rows for deterministic software tests."""
    rows: list[dict[str, object]] = []
    issue_date = date(2026, 7, 16)
    for member_index in range(3):
        for lead_day in range(1, 21):
            rows.append(
                {
                    "grid_id": "fixture-idaho-grid",
                    "latitude": 43.6,
                    "longitude": -116.2,
                    "elevation_m": 824.0,
                    "member_id": f"fixture-member-{member_index:02d}",
                    "valid_date": (issue_date + timedelta(days=lead_day)).isoformat(),
                    "tmax_c": 30.0 + member_index,
                    "tmin_c": 12.0 + member_index,
                    "vapor_pressure_kpa": 1.2,
                    "wind_m_s": 2.0,
                    "solar_mj_m2_day": 25.0,
                    "precip_mm": 0.5,
                }
            )
    return rows


def _normalized_bytes(rows: list[dict[str, object]]) -> bytes:
    payloads: list[dict[str, object]] = []
    for member in normalize_gefs_rows(rows, issued_at=ISSUED_AT):
        payload = asdict(member)
        payload["issued_at"] = ISSUED_AT
        payload["valid_date"] = member.valid_date.isoformat()
        payloads.append(payload)
    return "".join(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        for payload in payloads
    ).encode("utf-8")


def _write_daily_artifact(path: Path, rows: list[dict[str, object]]) -> bytes:
    normalized = _normalized_bytes(rows)
    artifact = {
        "artifact_type": "mlet.gefs.daily-artifact",
        "schema_version": 1,
        "provenance": {
            "idaho_bbox": list(IDAHO_BBOX),
            "source_issue_at": ISSUED_AT,
            "transform": {
                "name": "noaa-gefs-grib-to-daily-asce-input",
                "version": "1",
            },
            "upstream_raw_sha256": hashlib.sha256(b"fixture-grib-bytes").hexdigest(),
            "upstream_uri": "https://example.test/archived-gefs.grib2",
            "variables": VARIABLES,
        },
        "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
        "rows": rows,
    }
    artifact_bytes = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    path.write_bytes(artifact_bytes)
    return artifact_bytes


def test_gefs_normalizer_requires_twenty_distinct_daily_leads() -> None:
    members = normalize_gefs_rows(_gefs_rows(), issued_at=ISSUED_AT)

    assert len(members) == 60
    for member_id in {member.member_id for member in members}:
        leads = {
            member.valid_date
            for member in members
            if member.grid_id == "fixture-idaho-grid" and member.member_id == member_id
        }
        assert len(leads) == 20


def test_gefs_normalizer_rejects_missing_required_radiation() -> None:
    rows = _gefs_rows()
    del rows[0]["solar_mj_m2_day"]

    with pytest.raises(ValueError, match="solar_mj_m2_day"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_gefs_normalizer_rejects_duplicate_member_grid_day() -> None:
    rows = _gefs_rows()
    rows.append(rows[0].copy())

    with pytest.raises(ValueError, match="duplicate"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_gefs_normalizer_rejects_missing_daily_lead_for_one_member() -> None:
    rows = _gefs_rows()
    rows.pop()

    with pytest.raises(ValueError, match="exactly 20 daily leads"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_gefs_normalizer_rejects_non_finite_or_unsafe_weather_values() -> None:
    rows = _gefs_rows()
    rows[0]["wind_m_s"] = float("inf")

    with pytest.raises(ValueError, match="finite"):
        normalize_gefs_rows(rows, issued_at=ISSUED_AT)


def test_weather_fixture_is_conspicuously_non_scientific_and_complete() -> None:
    fixture_path = Path("examples/outlook/weather_members.jsonl")
    rows = [json.loads(line) for line in fixture_path.read_text().splitlines()]

    assert all(row["fixture_non_scientific"] is True for row in rows)
    assert len(normalize_gefs_rows(rows, issued_at=ISSUED_AT)) == 60


def test_fetch_gefs_refuses_live_grib_without_attempting_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempted = False

    def deny_network(*args: object, **kwargs: object) -> object:
        nonlocal attempted
        attempted = True
        raise AssertionError("network access must not be attempted")

    monkeypatch.setattr(socket, "create_connection", deny_network)

    with pytest.raises(NotImplementedError, match="GRIB decoder"):
        fetch_gefs(date(2026, 7, 16), IDAHO_BBOX, tmp_path / "weather.jsonl")

    assert attempted is False


def test_imported_daily_artifact_caches_exact_parsed_bytes_and_publishes_hashes(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "fixture.daily-artifact.json"
    artifact_bytes = _write_daily_artifact(artifact_path, _gefs_rows())
    destination = tmp_path / "weather_members.jsonl"

    output = materialize_gefs_daily_artifact(artifact_path, destination)

    assert output == destination
    assert len(destination.read_text().splitlines()) == 60
    receipt = json.loads(destination.with_suffix(".jsonl.source.json").read_text())
    assert receipt["raw_sha256"] == hashlib.sha256(artifact_bytes).hexdigest()
    assert receipt["normalized_sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()
    assert receipt["upstream_raw_sha256"] == hashlib.sha256(b"fixture-grib-bytes").hexdigest()
    assert receipt["source_issue_at"] == ISSUED_AT
    assert receipt["idaho_bbox"] == list(IDAHO_BBOX)
    assert receipt["variables"] == VARIABLES
    assert receipt["artifact_schema_version"] == 1
    assert receipt["transform"] == {
        "name": "noaa-gefs-grib-to-daily-asce-input",
        "version": "1",
    }
    cache_paths = list((tmp_path / "data" / "cache").glob("*.json"))
    assert len(cache_paths) == 1
    assert cache_paths[0].read_bytes() == artifact_bytes


def test_imported_daily_artifact_rejects_mismatched_declared_normalized_hash(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "fixture.daily-artifact.json"
    _write_daily_artifact(artifact_path, _gefs_rows())
    payload = json.loads(artifact_path.read_text())
    payload["normalized_sha256"] = "0" * 64
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="normalized_sha256"):
        materialize_gefs_daily_artifact(artifact_path, tmp_path / "weather_members.jsonl")


@pytest.mark.parametrize("failed_target", ("cache", "normalized", "receipt"))
def test_imported_daily_artifact_rolls_back_every_write_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_target: str
) -> None:
    artifact_path = tmp_path / "fixture.daily-artifact.json"
    _write_daily_artifact(artifact_path, _gefs_rows())
    destination = tmp_path / "weather_members.jsonl"

    from mlet.sources import gefs

    original_replace = gefs.os.replace
    failed = False

    def fail_one_stage(source: Path | str, target: Path | str) -> None:
        nonlocal failed
        target_path = Path(target)
        is_target = (
            (failed_target == "normalized" and target_path == destination)
            or (
                failed_target == "receipt"
                and target_path == destination.with_suffix(".jsonl.source.json")
            )
            or (failed_target == "cache" and target_path.parent.name == "cache")
        )
        if is_target and not failed:
            failed = True
            raise OSError("injected write-stage failure")
        original_replace(source, target)

    monkeypatch.setattr("mlet.sources.gefs.os.replace", fail_one_stage)

    with pytest.raises(OSError, match="injected write-stage failure"):
        materialize_gefs_daily_artifact(artifact_path, destination)

    assert not destination.exists()
    assert not destination.with_suffix(".jsonl.source.json").exists()
    assert not list((tmp_path / "data" / "cache").glob("*.json"))


def test_imported_daily_artifact_preserves_previous_completed_set_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_artifact = tmp_path / "first.daily-artifact.json"
    _write_daily_artifact(first_artifact, _gefs_rows())
    destination = tmp_path / "weather_members.jsonl"
    materialize_gefs_daily_artifact(first_artifact, destination)
    previous_normalized = destination.read_bytes()
    previous_receipt = destination.with_suffix(".jsonl.source.json").read_bytes()

    revised_rows = _gefs_rows()
    revised_rows[0]["tmax_c"] = 31.5
    revised_artifact = tmp_path / "revised.daily-artifact.json"
    _write_daily_artifact(revised_artifact, revised_rows)

    from mlet.sources import gefs

    original_replace = gefs.os.replace
    failed = False

    def fail_receipt(source: Path | str, target: Path | str) -> None:
        nonlocal failed
        if Path(target) == destination.with_suffix(".jsonl.source.json") and not failed:
            failed = True
            raise OSError("injected receipt failure")
        original_replace(source, target)

    monkeypatch.setattr("mlet.sources.gefs.os.replace", fail_receipt)

    with pytest.raises(OSError, match="injected receipt failure"):
        materialize_gefs_daily_artifact(revised_artifact, destination)

    assert destination.read_bytes() == previous_normalized
    assert destination.with_suffix(".jsonl.source.json").read_bytes() == previous_receipt
