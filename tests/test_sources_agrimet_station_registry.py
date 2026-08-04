"""Tests for the public AgriMet registry snapshot contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mlet.sources.agrimet_station_registry import (
    load_agrimet_station_registry,
    stations_for_state,
)


def _payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "mlet.agrimet.station-registry",
        "source_snapshot": {
            "json_uri": "https://example.test/stations.json",
            "json_sha256": "a" * 64,
            "csv_uri": "https://example.test/stations.csv",
            "csv_sha256": "b" * 64,
            "news_uri": "https://example.test/news.html",
            "news_sha256": "c" * 64,
            "retrieved_at": "2026-07-31T12:00:00Z",
        },
        "history_window": {"first": "2013-01-01", "last": "2019-12-31"},
        "stations": [
            {
                "station_id": "BOII",
                "description": "Boise",
                "state": "ID",
                "latitude": 43.6,
                "longitude": -116.2,
                "elevation_m": 824.0,
                "installation_date": "1995-07-26",
                "installation_date_raw": "7/26/1995",
                "station_uri": "https://example.test/boii",
                "responsibility": "pnro",
                "historical_location_status": "current_snapshot_only",
            },
            {
                "station_id": "ABEI",
                "description": "Aberdeen",
                "state": "ID",
                "latitude": 42.9,
                "longitude": -112.8,
                "elevation_m": None,
                "installation_date": None,
                "installation_date_raw": "",
                "station_uri": "https://example.test/abei",
                "responsibility": "noaa",
                "historical_location_status": "current_snapshot_only",
            },
        ],
    }


def test_registry_loads_and_filters_without_claiming_historical_coordinates(tmp_path: Path) -> None:
    """The current snapshot remains explicitly unsuitable as station history."""
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    snapshot = load_agrimet_station_registry(path)

    assert snapshot.history_first.isoformat() == "2013-01-01"
    assert [station.station_id for station in stations_for_state(snapshot, "id")] == [
        "BOII",
        "ABEI",
    ]
    assert all(
        station.historical_location_status == "current_snapshot_only"
        for station in snapshot.stations
    )


def test_registry_rejects_duplicate_station_ids(tmp_path: Path) -> None:
    """A duplicate station ID would make target identity ambiguous."""
    payload = _payload()
    stations = payload["stations"]
    assert isinstance(stations, list)
    stations[1]["station_id"] = "BOII"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unique"):
        load_agrimet_station_registry(path)


def test_registry_rejects_historical_status_in_current_snapshot(tmp_path: Path) -> None:
    """Only a separately verified history registry may resolve past locations."""
    payload = _payload()
    stations = payload["stations"]
    assert isinstance(stations, list)
    stations[0]["historical_location_status"] = "verified_history"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="current_snapshot_only"):
        load_agrimet_station_registry(path)
