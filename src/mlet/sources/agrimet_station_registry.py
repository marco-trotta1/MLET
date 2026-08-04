"""Parse the public USBR AgriMet station registry snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


_KIND = "mlet.agrimet.station-registry"


@dataclass(frozen=True)
class AgriMetStationRecord:
    """Current public metadata for one AgriMet station."""

    station_id: str
    description: str
    state: str
    latitude: float
    longitude: float
    elevation_m: Optional[float]
    installation_date: Optional[date]
    installation_date_raw: str
    station_uri: str
    responsibility: str
    historical_location_status: str


@dataclass(frozen=True)
class AgriMetStationRegistrySnapshot:
    """A checksum-bound current registry and its declared research window."""

    json_uri: str
    json_sha256: str
    csv_uri: str
    csv_sha256: str
    news_uri: str
    news_sha256: str
    retrieved_at: datetime
    history_first: date
    history_last: date
    stations: tuple[AgriMetStationRecord, ...]


def load_agrimet_station_registry(path: Path) -> AgriMetStationRegistrySnapshot:
    """Load a strict current registry snapshot without treating it as history."""
    try:
        payload = json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=_no_duplicates,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("AgriMet station registry must be duplicate-key-free UTF-8 JSON") from error
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "kind",
            "source_snapshot",
            "history_window",
            "stations",
        },
        "AgriMet station registry",
    )
    assert isinstance(payload, dict)
    if payload["schema_version"] != 1 or payload["kind"] != _KIND:
        raise ValueError("AgriMet station registry has an unsupported schema")
    source = _parse_source_snapshot(payload["source_snapshot"])
    window = payload["history_window"]
    _require_exact_keys(window, {"first", "last"}, "AgriMet history window")
    assert isinstance(window, dict)
    first = _parse_date(window["first"], "history_window.first")
    last = _parse_date(window["last"], "history_window.last")
    if first > last:
        raise ValueError("history_window.first must not be after history_window.last")
    raw_stations = payload["stations"]
    if not isinstance(raw_stations, list) or not raw_stations:
        raise ValueError("AgriMet station registry stations must be a non-empty list")
    stations = tuple(_parse_station(value) for value in raw_stations)
    station_ids = [station.station_id for station in stations]
    if len(set(station_ids)) != len(station_ids):
        raise ValueError("AgriMet station registry station IDs must be unique")
    return AgriMetStationRegistrySnapshot(
        json_uri=source["json_uri"],
        json_sha256=source["json_sha256"],
        csv_uri=source["csv_uri"],
        csv_sha256=source["csv_sha256"],
        news_uri=source["news_uri"],
        news_sha256=source["news_sha256"],
        retrieved_at=source["retrieved_at"],
        history_first=first,
        history_last=last,
        stations=stations,
    )


def stations_for_state(
    snapshot: AgriMetStationRegistrySnapshot,
    state: str,
) -> tuple[AgriMetStationRecord, ...]:
    """Return stations for one upper-case state without changing the snapshot."""
    if not isinstance(snapshot, AgriMetStationRegistrySnapshot):
        raise ValueError("AgriMet station registry snapshot is required")
    if not isinstance(state, str) or len(state) != 2 or not state.isascii():
        raise ValueError("state must be a two-letter ASCII code")
    normalized = state.upper()
    return tuple(station for station in snapshot.stations if station.state == normalized)


def _parse_source_snapshot(value: object) -> dict[str, object]:
    expected = {
        "json_uri",
        "json_sha256",
        "csv_uri",
        "csv_sha256",
        "news_uri",
        "news_sha256",
        "retrieved_at",
    }
    _require_exact_keys(value, expected, "AgriMet source snapshot")
    assert isinstance(value, dict)
    result = {
        "json_uri": _require_uri(value["json_uri"], "json_uri"),
        "json_sha256": _require_sha256(value["json_sha256"], "json_sha256"),
        "csv_uri": _require_uri(value["csv_uri"], "csv_uri"),
        "csv_sha256": _require_sha256(value["csv_sha256"], "csv_sha256"),
        "news_uri": _require_uri(value["news_uri"], "news_uri"),
        "news_sha256": _require_sha256(value["news_sha256"], "news_sha256"),
        "retrieved_at": _parse_utc(value["retrieved_at"], "retrieved_at"),
    }
    return result


def _parse_station(value: object) -> AgriMetStationRecord:
    expected = {
        "station_id",
        "description",
        "state",
        "latitude",
        "longitude",
        "elevation_m",
        "installation_date",
        "installation_date_raw",
        "station_uri",
        "responsibility",
        "historical_location_status",
    }
    _require_exact_keys(value, expected, "AgriMet station")
    assert isinstance(value, dict)
    station = _require_text(value["station_id"], "station_id").upper()
    if not station.isascii() or not station.isalnum():
        raise ValueError("station_id must contain only ASCII letters and digits")
    state = _require_text(value["state"], "state").upper()
    if len(state) != 2 or not state.isascii():
        raise ValueError("state must be a two-letter ASCII code")
    installation = value["installation_date"]
    parsed_installation = None if installation is None else _parse_date(installation, "installation_date")
    raw_installation = value["installation_date_raw"]
    if not isinstance(raw_installation, str):
        raise ValueError("installation_date_raw must be text")
    status = _require_text(value["historical_location_status"], "historical_location_status")
    if status != "current_snapshot_only":
        raise ValueError("current registry status must be current_snapshot_only")
    elevation = value["elevation_m"]
    parsed_elevation = None if elevation is None else _finite(elevation, "elevation_m", -500.0, 10_000.0)
    return AgriMetStationRecord(
        station_id=station,
        description=_require_text(value["description"], "description"),
        state=state,
        latitude=_finite(value["latitude"], "latitude", -90.0, 90.0),
        longitude=_finite(value["longitude"], "longitude", -180.0, 180.0),
        elevation_m=parsed_elevation,
        installation_date=parsed_installation,
        installation_date_raw=raw_installation,
        station_uri=_require_uri(value["station_uri"], "station_uri"),
        responsibility=_require_text(value["responsibility"], "responsibility"),
        historical_location_status=status,
    )


def _require_exact_keys(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields must match the schema exactly")


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _parse_date(value: object, label: str) -> date:
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


def _require_uri(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an absolute URI")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} must be an absolute HTTP URI")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label} must be lowercase SHA-256 hexadecimal")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be lowercase SHA-256 hexadecimal")
    return value


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
