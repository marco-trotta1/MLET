"""Tests for ETo target artifacts assembled from independent station records."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

from mlet.outlook.contracts import WeatherMember
from mlet.outlook.eto_archive import (
    SourceTiming,
    assemble_eto_hindcast_evidence,
    build_eto_target_artifact,
)
from mlet.outlook.eto_build import write_eto_outlook
from mlet.outlook.eto_hindcast import evaluate_eto_hindcast_evidence
from mlet.outlook.manifest import build_manifest
from mlet.sources.agrimet import AgriMetEtosObservation, AgriMetGridMatch


def test_eto_target_artifact_keeps_station_identity_and_baseline_separate_from_grid_id(
    tmp_path: Path,
) -> None:
    """Replacing the station target ID with a grid ID must fail this evidence contract."""
    observation = AgriMetEtosObservation(
        station_id="BOIS",
        latitude=43.6,
        longitude=-116.2,
        elevation_m=824.0,
        valid_date=date(2019, 7, 2),
        etos_mm=5.08,
        available_at=datetime(2019, 7, 3, 12, tzinfo=timezone.utc),
        uri="https://www.usbr.gov/pn/agrimet/archive/BOIS",
        source_version="agrimet-archive-v1",
    )
    destination = tmp_path / "targets.json"

    build_eto_target_artifact(
        case_id="2019-07-01-fold-4",
        run_id="run-1",
        issue_time=datetime(2019, 7, 1, 18, tzinfo=timezone.utc),
        observations=(observation,),
        matches={
            "BOIS": AgriMetGridMatch(
                station_id="BOIS", grid_id="43:-117", distance_km=11.0
            )
        },
        baseline_p50_mm={("BOIS", date(2019, 7, 2)): 4.5},
        destination=destination,
        exclusions=(
            {
                "target_id": "agrimet:BOIS",
                "valid_date": date(2019, 7, 3),
                "reason": "published_missing_etos",
            },
        ),
    )

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["kind"] == "idaho_outlook_eto_hindcast_target"
    assert payload["values"] == [
        {
            "target_id": "agrimet:BOIS",
            "grid_id": "43:-117",
            "latitude": 43.6,
            "longitude": -116.2,
            "lead_day": 1,
            "valid_date": "2019-07-02",
            "target_mm": 5.08,
            "baseline_p50_mm": 4.5,
            "target_kind": "independent_asce_short_reference_eto",
        }
    ]
    assert payload["exclusions"] == [
        {
            "target_id": "agrimet:BOIS",
            "valid_date": "2019-07-03",
            "reason": "published_missing_etos",
        }
    ]


def test_eto_evidence_assembler_writes_v4_without_scenario_receipts(
    tmp_path: Path,
) -> None:
    """Adding scenario receipts to ETo v4 must fail this archive boundary."""
    issue_time = datetime(2019, 7, 1, 18, tzinfo=timezone.utc)
    source = tmp_path / "weather.jsonl"
    source.write_text('{"weather":"archived"}\n', encoding="utf-8")
    manifest = build_manifest(
        "2019-07-01T18:00:00Z",
        {"weather": source},
        "test-revision",
        "2026-08-04T18:08:54.243122Z",
    )
    forecast_directory = tmp_path / "forecast"
    forecast_directory.mkdir()
    members = tuple(
        WeatherMember(
            grid_id="43:-117",
            latitude=43.5,
            longitude=-116.5,
            elevation_m=824.0,
            member_id=f"member-{member_index}",
            issued_at=issue_time,
            valid_date=date(2019, 7, 1 + lead_day),
            tmax_c=30.0,
            tmin_c=12.0,
            vapor_pressure_kpa=1.2,
            wind_m_s=2.0,
            solar_mj_m2_day=25.0,
            precip_mm=0.0,
        )
        for member_index in range(3)
        for lead_day in range(1, 21)
    )
    manifest = write_eto_outlook(members, manifest, forecast_directory)
    observation = AgriMetEtosObservation(
        station_id="BOIS",
        latitude=43.6,
        longitude=-116.2,
        elevation_m=824.0,
        valid_date=date(2019, 7, 2),
        etos_mm=5.08,
        available_at=datetime(2019, 7, 3, 12, tzinfo=timezone.utc),
        uri="https://www.usbr.gov/pn/agrimet/archive/BOIS",
        source_version="agrimet-archive-v1",
    )
    target_path = tmp_path / "target.json"
    build_eto_target_artifact(
        case_id="2019-07-01-fold-4",
        run_id=manifest.run_id,
        issue_time=issue_time,
        observations=(observation,),
        matches={
            "BOIS": AgriMetGridMatch(
                station_id="BOIS", grid_id="43:-117", distance_km=11.0
            )
        },
        baseline_p50_mm={("BOIS", date(2019, 7, 2)): 4.5},
        destination=target_path,
    )
    destination = tmp_path / "evidence"
    destination.mkdir()

    evidence_path = assemble_eto_hindcast_evidence(
        case_id="2019-07-01-fold-4",
        issue_time=issue_time,
        forecast_directory=forecast_directory,
        target_path=target_path,
        source_timing={
            "weather": SourceTiming(
                temporal_role="retrospective_reforecast",
                source_issue_at=issue_time,
                archive_available_at=datetime(
                    2026, 8, 4, 18, 8, 54, 243122, tzinfo=timezone.utc
                ),
            )
        },
        held_out_fold=4,
        held_out_season="JJA",
        destination=destination,
    )

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["schema_version"] == 4
    assert "scenario_receipt_artifacts" not in evidence["cases"][0]
    source_receipt_path = destination / "receipts" / "source-weather.json"
    source_receipt = json.loads(source_receipt_path.read_text(encoding="utf-8"))
    assert source_receipt["schema_version"] == 2
    assert source_receipt["temporal_role"] == "retrospective_reforecast"
    assert source_receipt["source_issue_at"] == "2019-07-01T18:00:00Z"
    assert source_receipt["archive_available_at"] == "2026-08-04T18:08:54.243122Z"
    assert "available_at" not in source_receipt
    assert evaluate_eto_hindcast_evidence(evidence_path).case_count == 1
