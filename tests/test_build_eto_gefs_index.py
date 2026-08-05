"""Tests for the GEFS case index builder."""

from datetime import date, datetime, timezone
import json
from pathlib import Path

from mlet.outlook.contracts import WeatherMember
from mlet.outlook.dates import outlook_valid_dates
from mlet.outlook.manifest import build_manifest
from mlet.outlook.eto_build import write_eto_outlook
from scripts.build_eto_gefs_index import build_gefs_case_index


def test_gefs_case_index_keeps_only_station_season_support(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    candidates = root / "candidates"
    candidate = candidates / "2019070300"
    candidate.mkdir(parents=True)
    source = root / "source.json"
    source.write_text("{}\n", encoding="utf-8")
    manifest = build_manifest(
        "2019-07-03T00:00:00Z",
        {"gefs": source},
        "test-revision",
        "2019-07-03T00:00:00Z",
    )
    members = tuple(
        WeatherMember(
            grid_id="43.50:-116.00",
            latitude=43.5,
            longitude=-116.0,
            elevation_m=829.0,
            member_id=f"member-{member}",
            issued_at=datetime(2019, 7, 3, tzinfo=timezone.utc),
            valid_date=valid_date,
            tmax_c=30.0,
            tmin_c=12.0,
            vapor_pressure_kpa=1.2,
            wind_m_s=2.0,
            solar_mj_m2_day=25.0,
            precip_mm=0.0,
        )
        for member in range(3)
        for valid_date in outlook_valid_dates(datetime(2019, 7, 3, tzinfo=timezone.utc))
    )
    write_eto_outlook(members, manifest, candidate)

    stream_index = root / "stream-index.json"
    stream_index.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "mlet.gefs.reforecast-stream-index",
                "plan_sha256": "a" * 64,
                "issue_count": 1,
                "issues": [
                    {
                        "issue_time": "2019-07-03T00:00:00Z",
                        "candidate_path": "2019070300",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "station_id": "BOII",
            "latitude": 43.6,
            "longitude": -116.2,
            "elevation_m": 829.0,
            "valid_date": f"{year}-07-03",
            "etos_in": value,
            "available_at": f"{year}-07-04T12:00:00Z",
            "uri": "https://example.test/boii",
            "source_version": "source-v1",
        }
        for year, value in ((2018, 0.2), (2019, 0.3))
    ]
    rows_path = root / "rows.json"
    rows_path.write_text(json.dumps(rows), encoding="utf-8")
    mapping_path = root / "mapping.json"
    mapping_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "mlet.agrimet.gefs-grid-mapping",
                "forecast_artifact_sha256": "b" * 64,
                "maximum_distance_km": 50.0,
                "mappings": [
                    {
                        "station_id": "BOII",
                        "grid_id": "43.50:-116.00",
                        "latitude": 43.6,
                        "longitude": -116.2,
                        "distance_km": 18.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    index_path = root / "gefs-index.json"

    build_gefs_case_index(
        stream_index=stream_index,
        candidate_root=candidates,
        rows_path=rows_path,
        mapping_path=mapping_path,
        destination=index_path,
    )

    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert len(payload["issues"]) == 1
    assert payload["issues"][0]["case_id"] == (
        "issue-20190703-station-BOII-season-JJA-fold-2"
    )
    assert payload["issues"][0]["held_out_fold"] == 2
    assert payload["issues"][0]["held_out_season"] == "JJA"
    assert payload["issues"][0]["forecast_directory"] == "candidates/2019070300"
