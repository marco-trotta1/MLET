"""Load checksum-bound historical locations for AgriMet ETo stations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
from typing import Mapping, Optional, Union
from urllib.parse import urlparse


@dataclass(frozen=True)
class AgriMetStationLocation:
    """One verified station location over one inclusive historical interval."""

    station_id: str
    valid_from: date
    valid_to: Optional[date]
    latitude: float
    longitude: float
    elevation_m: float
    metadata_uri: str
    metadata_sha256: str
    source_version: str


@dataclass(frozen=True)
class AgriMetStationHistoryRegistry:
    """Immutable station history indexed by upper-case station identifier."""

    locations_by_station: Mapping[str, tuple[AgriMetStationLocation, ...]]


def load_agrimet_station_history_registry(path: Path) -> AgriMetStationHistoryRegistry:
    """Load a strict historical location registry without implicit station moves."""
    try:
        payload = json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=_no_duplicates,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("AgriMet station history must be duplicate-key-free UTF-8 JSON") from error
    _require_exact_keys(
        payload,
        {"schema_version", "kind", "source_snapshot", "stations"},
        "AgriMet station history",
    )
    assert isinstance(payload, dict)
    if payload["schema_version"] != 1 or payload["kind"] != "mlet.agrimet.station-history-registry":
        raise ValueError("AgriMet station history has an unsupported schema")
    _validate_source_snapshot(payload["source_snapshot"])
    raw_stations = payload["stations"]
    if not isinstance(raw_stations, list) or not raw_stations:
        raise ValueError("AgriMet station history stations must be a non-empty list")
    locations_by_station: dict[str, tuple[AgriMetStationLocation, ...]] = {}
    for raw_station in raw_stations:
        _require_exact_keys(raw_station, {"station_id", "segments"}, "AgriMet station")
        assert isinstance(raw_station, dict)
        station_id = _station_id(raw_station["station_id"])
        if station_id in locations_by_station:
            raise ValueError("AgriMet station history must not duplicate station_id")
        locations_by_station[station_id] = _parse_segments(station_id, raw_station["segments"])
    return AgriMetStationHistoryRegistry(locations_by_station=locations_by_station)


def resolve_agrimet_station_location(
    registry: AgriMetStationHistoryRegistry,
    station_id: str,
    valid_date: Union[date, str],
) -> AgriMetStationLocation:
    """Return the only checksum-bound location valid for one station-day."""
    if not isinstance(registry, AgriMetStationHistoryRegistry):
        raise ValueError("AgriMet station history registry is required")
    station = _station_id(station_id)
    day = _parse_date(valid_date, "valid_date")
    try:
        locations = registry.locations_by_station[station]
    except KeyError as error:
        raise ValueError("AgriMet station is absent from the historical registry") from error
    matches = [
        location
        for location in locations
        if location.valid_from <= day
        and (location.valid_to is None or day <= location.valid_to)
    ]
    if len(matches) != 1:
        raise ValueError("AgriMet station-day has no verified historical location")
    return matches[0]


def _parse_segments(
    station_id: str,
    raw_segments: object,
) -> tuple[AgriMetStationLocation, ...]:
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("AgriMet station history segments must be a non-empty list")
    expected = {
        "valid_from",
        "valid_to",
        "latitude",
        "longitude",
        "elevation_m",
        "metadata_uri",
        "metadata_sha256",
        "source_version",
    }
    locations = []
    for raw_segment in raw_segments:
        _require_exact_keys(raw_segment, expected, "AgriMet station segment")
        assert isinstance(raw_segment, dict)
        valid_from = _parse_date(raw_segment["valid_from"], "valid_from")
        valid_to = (
            None
            if raw_segment["valid_to"] is None
            else _parse_date(raw_segment["valid_to"], "valid_to")
        )
        if valid_to is not None and valid_to < valid_from:
            raise ValueError("AgriMet station segment valid_to must not precede valid_from")
        locations.append(
            AgriMetStationLocation(
                station_id=station_id,
                valid_from=valid_from,
                valid_to=valid_to,
                latitude=_finite(raw_segment["latitude"], "latitude", -90.0, 90.0),
                longitude=_finite(raw_segment["longitude"], "longitude", -180.0, 180.0),
                elevation_m=_finite(
                    raw_segment["elevation_m"], "elevation_m", -500.0, 10_000.0
                ),
                metadata_uri=_require_uri(raw_segment["metadata_uri"]),
                metadata_sha256=_require_sha256(
                    raw_segment["metadata_sha256"], "metadata_sha256"
                ),
                source_version=_require_text(raw_segment["source_version"], "source_version"),
            )
        )
    ordered = tuple(sorted(locations, key=lambda location: location.valid_from))
    for previous, current in zip(ordered, ordered[1:]):
        if previous.valid_to is None or current.valid_from <= previous.valid_to:
            raise ValueError("AgriMet station history segments overlap")
    return ordered


def _validate_source_snapshot(value: object) -> None:
    _require_exact_keys(
        value,
        {"uri", "sha256", "retrieved_at"},
        "AgriMet station history source_snapshot",
    )
    assert isinstance(value, dict)
    _require_uri(value["uri"])
    _require_sha256(value["sha256"], "AgriMet source_snapshot sha256")
    _parse_utc(value["retrieved_at"], "AgriMet source_snapshot retrieved_at")


def _require_exact_keys(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields must match the schema exactly")


def _station_id(value: object) -> str:
    station = _require_text(value, "station_id").upper()
    if not station.isascii() or not station.isalnum():
        raise ValueError("station_id must contain only ASCII letters and digits")
    return station


def _parse_date(value: Union[date, str, object], label: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{label} must be ISO date text")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be ISO date text") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be ISO date text")
    return parsed


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be strict UTC ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be strict UTC ISO-8601 text") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be strict UTC ISO-8601 text")
    return parsed.astimezone(timezone.utc)


def _finite(value: object, label: str, lower: float, upper: float) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or not lower <= result <= upper:
        raise ValueError(f"{label} is outside its valid range")
    return result


def _require_uri(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("AgriMet URI must be absolute")
    parsed = urlparse(value)
    if not parsed.scheme or (parsed.scheme != "file" and not parsed.netloc):
        raise ValueError("AgriMet URI must be absolute")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label} must be lowercase SHA-256 hexadecimal")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be lowercase SHA-256 hexadecimal")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
