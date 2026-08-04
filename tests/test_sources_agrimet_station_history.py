"""Tests for the immutable AgriMet station-history registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mlet.sources.agrimet_station_history import (
    load_agrimet_station_history_registry,
    resolve_agrimet_station_location,
)


def _registry() -> dict[str, object]:
    """Return a registry with an explicit station relocation."""
    return {
        "schema_version": 1,
        "kind": "mlet.agrimet.station-history-registry",
        "source_snapshot": {
            "uri": "https://www.usbr.gov/pn/agrimet/agrimetmap/usbr_map.json",
            "sha256": "a" * 64,
            "retrieved_at": "2026-07-29T08:00:00Z",
        },
        "stations": [
            {
                "station_id": "BOII",
                "segments": [
                    {
                        "valid_from": "2010-01-01",
                        "valid_to": "2015-12-31",
                        "latitude": 43.60,
                        "longitude": -116.20,
                        "elevation_m": 824.0,
                        "metadata_uri": "https://example.test/boii-history-1",
                        "metadata_sha256": "b" * 64,
                        "source_version": "station-history-v1",
                    },
                    {
                        "valid_from": "2016-01-01",
                        "valid_to": None,
                        "latitude": 43.61,
                        "longitude": -116.19,
                        "elevation_m": 826.0,
                        "metadata_uri": "https://example.test/boii-history-2",
                        "metadata_sha256": "c" * 64,
                        "source_version": "station-history-v2",
                    },
                ],
            }
        ],
    }


def test_station_history_resolves_the_location_for_each_historical_day(
    tmp_path: Path,
) -> None:
    """Current metadata must not overwrite the location of an old target."""
    path = tmp_path / "station-history.json"
    path.write_text(json.dumps(_registry()), encoding="utf-8")

    registry = load_agrimet_station_history_registry(path)

    old_location = resolve_agrimet_station_location(registry, "BOII", "2015-07-01")
    new_location = resolve_agrimet_station_location(registry, "BOII", "2019-07-01")
    assert old_location.latitude == 43.60
    assert new_location.latitude == 43.61
    assert old_location.source_version == "station-history-v1"


def test_station_history_rejects_overlapping_location_segments(tmp_path: Path) -> None:
    """One station-day cannot have two candidate grid locations."""
    payload = _registry()
    station = payload["stations"][0]
    assert isinstance(station, dict)
    segments = station["segments"]
    assert isinstance(segments, list)
    segments[1]["valid_from"] = "2015-12-31"
    path = tmp_path / "station-history.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="overlap"):
        load_agrimet_station_history_registry(path)
