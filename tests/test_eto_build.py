"""Tests for the narrow ETo-only research-candidate contract."""

from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

from mlet.outlook.contracts import WeatherMember
from mlet.outlook.eto_build import (
    build_eto_outlook_from_gefs,
    serialize_eto_outlook,
    write_eto_outlook,
)
from mlet.outlook.manifest import build_manifest
from mlet.sources.gefs import materialize_gefs_daily_artifact, normalize_gefs_rows


def test_eto_builder_emits_only_eto_with_the_pending_evaluation_scope(
    tmp_path: Path,
) -> None:
    """Adding an ETc or ETa output to the ETo artifact must fail this contract."""
    source = tmp_path / "weather.jsonl"
    source.write_text('{"weather":"archived"}\n', encoding="utf-8")
    manifest = build_manifest(
        "2026-07-01T18:00:00Z",
        {"weather": source},
        "test-revision",
        "2026-07-01T18:00:00Z",
    )
    members = []
    for member_index in range(3):
        for lead_day in range(1, 21):
            members.append(
                WeatherMember(
                    grid_id="43:-117",
                    latitude=43.5,
                    longitude=-116.5,
                    elevation_m=824.0,
                    member_id=f"member-{member_index}",
                    issued_at=manifest.issued_at,
                    valid_date=manifest.issued_at.date() + timedelta(days=lead_day),
                    tmax_c=30.0,
                    tmin_c=12.0,
                    vapor_pressure_kpa=1.2,
                    wind_m_s=2.0,
                    solar_mj_m2_day=25.0,
                    precip_mm=0.0,
                )
            )

    payload = json.loads(serialize_eto_outlook(members, manifest).decode("utf-8"))

    assert payload["fixture_non_scientific"] is False
    assert payload["production_status"] == "research_candidate"
    assert payload["promotion_status"] == "not_promoted"
    assert payload["validation_status"] == "evaluation_pending"
    assert payload["validation_scope"]["formal_hindcast_layers"] == ["eto_mm"]
    assert len(payload["feature_collections"]) == 20
    assert set(payload["feature_collections"][0]["features"][0]["properties"]["layers"]) == {
        "eto_mm"
    }


def test_eto_builder_binds_outlook_bytes_to_the_final_manifest(tmp_path: Path) -> None:
    """Changing the written outlook bytes must fail the manifest hash contract."""
    source = tmp_path / "weather.jsonl"
    source.write_text('{"weather":"archived"}\n', encoding="utf-8")
    manifest = build_manifest(
        "2026-07-01T18:00:00Z",
        {"weather": source},
        "test-revision",
        "2026-07-01T18:00:00Z",
    )
    members = [
        WeatherMember(
            grid_id="43:-117",
            latitude=43.5,
            longitude=-116.5,
            elevation_m=824.0,
            member_id=f"member-{member_index}",
            issued_at=manifest.issued_at,
            valid_date=manifest.issued_at.date() + timedelta(days=lead_day),
            tmax_c=30.0,
            tmin_c=12.0,
            vapor_pressure_kpa=1.2,
            wind_m_s=2.0,
            solar_mj_m2_day=25.0,
            precip_mm=0.0,
        )
        for member_index in range(3)
        for lead_day in range(1, 21)
    ]
    destination = tmp_path / "candidate"
    destination.mkdir()

    completed = write_eto_outlook(members, manifest, destination)

    assert json.loads((destination / "manifest.json").read_text()) == json.loads(
        completed.to_json()
    )
    assert completed.artifact_sha256 == (
        ("outlook.json", hashlib.sha256((destination / "outlook.json").read_bytes()).hexdigest()),
    )


def test_eto_builder_materializes_an_operational_candidate_from_pinned_gefs(
    tmp_path: Path,
) -> None:
    """The candidate must inherit its run receipt from verified GEFS bytes."""
    issue_time = "2026-07-16T18:00:00Z"
    rows = [
        {
            "grid_id": "43:-117",
            "latitude": 43.5,
            "longitude": -116.5,
            "elevation_m": 824.0,
            "member_id": f"member-{member_index}",
            "valid_date": (date(2026, 7, 16) + timedelta(days=lead_day)).isoformat(),
            "tmax_c": 30.0,
            "tmin_c": 12.0,
            "vapor_pressure_kpa": 1.2,
            "wind_m_s": 2.0,
            "solar_mj_m2_day": 25.0,
            "precip_mm": 0.0,
        }
        for member_index in range(3)
        for lead_day in range(1, 21)
    ]
    normalized = "".join(
        json.dumps(
            {
                **member.__dict__,
                "issued_at": issue_time,
                "valid_date": member.valid_date.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        for member in normalize_gefs_rows(rows, issued_at=issue_time)
    ).encode("utf-8")
    artifact = {
        "artifact_type": "mlet.gefs.daily-artifact",
        "schema_version": 1,
        "provenance": {
            "idaho_bbox": [-117.25, 42.0, -111.0, 49.0],
            "daily_aggregation_timezone": "America/Boise",
            "source_issue_at": issue_time,
            "transform": {
                "name": "noaa-gefs-grib-to-daily-asce-input",
                "version": "1",
            },
            "upstream_raw_sha256": hashlib.sha256(b"archived-gefs").hexdigest(),
            "upstream_uri": "https://example.test/gefs.grib2",
            "variables": [
                "precip_mm",
                "solar_mj_m2_day",
                "tmax_c",
                "tmin_c",
                "vapor_pressure_kpa",
                "wind_m_s",
            ],
        },
        "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
        "rows": rows,
    }
    artifact_path = tmp_path / "gefs.daily-artifact.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    artifact_set = materialize_gefs_daily_artifact(
        artifact_path, tmp_path / "weather_members.gefs"
    )
    destination = tmp_path / "candidate"
    destination.mkdir()

    manifest = build_eto_outlook_from_gefs(
        artifact_set=artifact_set,
        git_revision="test-revision",
        retrieved_at=issue_time,
        destination=destination,
    )

    assert manifest.issued_at.isoformat() == "2026-07-16T18:00:00+00:00"
    assert manifest.sources[0].uri == "https://example.test/gefs.grib2"
    assert manifest.sources[0].sha256 == hashlib.sha256(
        artifact_path.read_bytes()
    ).hexdigest()
    assert (destination / "outlook.json").is_file()
