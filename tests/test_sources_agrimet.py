"""Tests for independent AgriMet ASCE grass-reference ETo targets."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from mlet.sources.agrimet import (
    AgriMetEtosObservation,
    agrimet_etos_archive_uri,
    map_agrimet_station_to_grid,
    materialize_agrimet_etos_artifact,
    normalize_agrimet_etos_rows,
    parse_agrimet_etos_archive_response,
    parse_agrimet_etos_archive_response_with_station_history,
)
from mlet.sources.agrimet_station_history import (
    AgriMetStationHistoryRegistry,
    AgriMetStationLocation,
)


def test_normalize_agrimet_etos_rows_converts_published_inches_to_millimeters() -> None:
    """Changing the inch-to-mm conversion must fail this target contract."""
    observations = normalize_agrimet_etos_rows(
        [
            {
                "station_id": "BOIS",
                "latitude": 43.6,
                "longitude": -116.2,
                "elevation_m": 824.0,
                "valid_date": "2019-07-01",
                "etos_in": 0.2,
                "available_at": "2019-07-02T12:00:00Z",
                "uri": "https://www.usbr.gov/pn/agrimet/archive/BOIS",
                "source_version": "agrimet-archive-v1",
            }
        ]
    )

    assert len(observations) == 1
    observation = observations[0]
    assert observation.station_id == "BOIS"
    assert observation.valid_date == date(2019, 7, 1)
    assert observation.etos_mm == pytest.approx(5.08)
    assert observation.available_at == datetime(2019, 7, 2, 12, tzinfo=timezone.utc)


def test_agrimet_archive_uri_is_fixed_for_one_station_date_interval() -> None:
    """A target archive request must not depend on an interactive web form."""
    assert agrimet_etos_archive_uri(
        "boii",
        date(2019, 7, 1),
        date(2019, 7, 3),
    ) == (
        "https://www.usbr.gov/pn-bin/webarccsv.pl?"
        "parameter=BOII%20ETOS&syer=2019&smnth=7&sdy=1&"
        "eyer=2019&emnth=7&edy=3"
    )


def test_normalize_agrimet_etos_rows_rejects_missing_values() -> None:
    """A missing independent target must never be converted to zero."""
    row = {
        "station_id": "BOIS",
        "latitude": 43.6,
        "longitude": -116.2,
        "elevation_m": 824.0,
        "valid_date": "2019-07-01",
        "etos_in": None,
        "available_at": "2019-07-02T12:00:00Z",
        "uri": "https://www.usbr.gov/pn/agrimet/archive/BOIS",
        "source_version": "agrimet-archive-v1",
    }

    with pytest.raises(ValueError, match="etos_in"):
        normalize_agrimet_etos_rows([row])


def test_normalize_agrimet_etos_rows_rejects_target_available_before_local_day_end() -> None:
    """A target must be available after the Idaho civil day it describes."""
    row = {
        "station_id": "BOIS",
        "latitude": 43.6,
        "longitude": -116.2,
        "elevation_m": 824.0,
        "valid_date": "2019-07-01",
        "etos_in": 0.2,
        "available_at": "2019-07-02T05:00:00Z",
        "uri": "https://www.usbr.gov/pn/agrimet/archive/BOIS",
        "source_version": "agrimet-archive-v1",
    }

    with pytest.raises(ValueError, match="available_at"):
        normalize_agrimet_etos_rows([row])


def test_agrimet_artifact_binds_raw_rows_to_normalized_millimeter_targets(
    tmp_path: Path,
) -> None:
    """Changing raw station rows must fail the raw-to-normalized hash binding."""
    source = tmp_path / "agrimet.json"
    source.write_text(
        json.dumps(
            [
                {
                    "station_id": "BOIS",
                    "latitude": 43.6,
                    "longitude": -116.2,
                    "elevation_m": 824.0,
                    "valid_date": "2019-07-01",
                    "etos_in": 0.2,
                    "available_at": "2019-07-02T12:00:00Z",
                    "uri": "https://www.usbr.gov/pn/agrimet/archive/BOIS",
                    "source_version": "agrimet-archive-v1",
                }
            ]
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "agrimet-etos.json"

    artifact_path = materialize_agrimet_etos_artifact(source, destination)

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["artifact_type"] == "mlet.agrimet.etos-artifact"
    assert artifact["raw_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert artifact["rows"][0]["etos_mm"] == pytest.approx(5.08)


def test_agrimet_station_maps_to_the_nearest_forecast_grid_with_a_distance_limit() -> None:
    """Changing the nearest-grid rule must fail the target-identity contract."""
    observation = AgriMetEtosObservation(
        station_id="BOIS",
        latitude=43.6,
        longitude=-116.2,
        elevation_m=824.0,
        valid_date=date(2019, 7, 1),
        etos_mm=5.08,
        available_at=datetime(2019, 7, 2, 12, tzinfo=timezone.utc),
        uri="https://www.usbr.gov/pn/agrimet/archive/BOIS",
        source_version="agrimet-archive-v1",
    )

    match = map_agrimet_station_to_grid(
        observation,
        {"near": (43.5, -116.1), "far": (45.0, -114.0)},
        maximum_distance_km=30.0,
    )

    assert match.grid_id == "near"
    assert 0.0 < match.distance_km < 30.0


def test_agrimet_archive_parser_keeps_missing_days_as_explicit_exclusions() -> None:
    """A published missing ETos value must not become a zero-valued target."""
    response = """BEGIN DATA
DATE      ,   BOII ETOS
07/01/2019,        0.20
07/02/2019,           m
END DATA
"""

    parsed = parse_agrimet_etos_archive_response(
        response,
        station_id="BOII",
        latitude=43.6,
        longitude=-116.2,
        elevation_m=824.0,
        retrieved_at="2019-07-03T12:00:00Z",
        uri="https://www.usbr.gov/pn-bin/webarccsv.pl?parameter=BOII%20ETOS",
        source_version="agrimet-archive-v1",
    )

    assert parsed.rows[0]["etos_in"] == pytest.approx(0.20)
    assert parsed.excluded_dates == (date(2019, 7, 2),)


def test_agrimet_archive_parser_keeps_an_all_missing_interval_for_exclusion() -> None:
    """An all-missing station interval is valid source evidence, not a crash."""
    response = """BEGIN DATA
DATE,BOII ETOS
07/01/2019,m
END DATA
"""

    parsed = parse_agrimet_etos_archive_response(
        response,
        station_id="BOII",
        latitude=43.6,
        longitude=-116.2,
        elevation_m=824.0,
        retrieved_at="2019-07-03T12:00:00Z",
        uri="https://www.usbr.gov/pn-bin/webarccsv.pl?parameter=BOII%20ETOS",
        source_version="agrimet-archive-v1",
    )

    assert parsed.rows == ()
    assert parsed.excluded_dates == (date(2019, 7, 1),)


def test_agrimet_archive_parser_keeps_no_record_as_an_explicit_exclusion() -> None:
    """The official archive uses NO RECORD for a station without a value."""
    response = """BEGIN DATA
DATE,BOII ETOS
07/01/2019,NO RECORD
END DATA
"""

    parsed = parse_agrimet_etos_archive_response(
        response,
        station_id="BOII",
        latitude=43.6,
        longitude=-116.2,
        elevation_m=824.0,
        retrieved_at="2019-07-03T12:00:00Z",
        uri="https://www.usbr.gov/pn-bin/webarccsv.pl?parameter=BOII%20ETOS",
        source_version="agrimet-archive-v1",
    )

    assert parsed.rows == ()
    assert parsed.excluded_dates == (date(2019, 7, 1),)


def test_agrimet_archive_parser_resolves_each_target_day_through_station_history() -> None:
    """A station relocation must change target coordinates on its effective date."""
    registry = AgriMetStationHistoryRegistry(
        locations_by_station={
            "BOII": (
                AgriMetStationLocation(
                    station_id="BOII",
                    valid_from=date(2019, 7, 1),
                    valid_to=date(2019, 7, 1),
                    latitude=43.60,
                    longitude=-116.20,
                    elevation_m=824.0,
                    metadata_uri="https://example.test/old",
                    metadata_sha256="a" * 64,
                    source_version="old-location",
                ),
                AgriMetStationLocation(
                    station_id="BOII",
                    valid_from=date(2019, 7, 2),
                    valid_to=None,
                    latitude=43.61,
                    longitude=-116.19,
                    elevation_m=826.0,
                    metadata_uri="https://example.test/new",
                    metadata_sha256="b" * 64,
                    source_version="new-location",
                ),
            )
        }
    )
    response = """BEGIN DATA
DATE,BOII ETOS
07/01/2019,0.20
07/02/2019,0.25
END DATA
"""

    parsed = parse_agrimet_etos_archive_response_with_station_history(
        response,
        station_id="BOII",
        station_history=registry,
        retrieved_at="2019-07-03T12:00:00Z",
        uri="https://www.usbr.gov/pn-bin/webarccsv.pl?parameter=BOII%20ETOS",
        source_version="raw-response-sha256",
    )

    assert parsed.rows[0]["latitude"] == pytest.approx(43.60)
    assert parsed.rows[1]["latitude"] == pytest.approx(43.61)
