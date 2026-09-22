"""Normalize published USBR AgriMet ETos observations.

AgriMet publishes ETos as ASCE-EWRI grass-reference ET in inches per day.
This module preserves the station identity and source receipt. It does not
calculate ETo from MLET forecast inputs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

from mlet.outlook.dates import idaho_local_day_end_utc
from mlet.sources.agrimet_station_history import (
    AgriMetStationHistoryRegistry,
    resolve_agrimet_station_location,
)


_INCH_TO_MILLIMETER = 25.4
_ARTIFACT_TYPE = "mlet.agrimet.etos-artifact"
_ARTIFACT_SCHEMA_VERSION = 1
_ARCHIVE_URI = "https://www.usbr.gov/pn-bin/webarccsv.pl"


@dataclass(frozen=True)
class AgriMetEtosObservation:
    """One published, independent daily AgriMet grass-reference ET target."""

    station_id: str
    latitude: float
    longitude: float
    elevation_m: float
    valid_date: date
    etos_mm: float
    available_at: datetime
    uri: str
    source_version: str


@dataclass(frozen=True)
class AgriMetGridMatch:
    """One deterministic station-to-forecast-grid identity binding."""

    station_id: str
    grid_id: str
    distance_km: float


@dataclass(frozen=True)
class ParsedAgriMetEtosArchive:
    """Raw ETos rows and explicit exclusions from one archive response."""

    rows: tuple[dict[str, object], ...]
    excluded_dates: tuple[date, ...]


def agrimet_etos_archive_uri(station_id: str, first_date: date, last_date: date) -> str:
    """Return the fixed official ETos archive request for one station interval."""
    station = _require_text(station_id, "station_id").upper()
    first = _require_calendar_date(first_date, "first_date")
    last = _require_calendar_date(last_date, "last_date")
    if first > last:
        raise ValueError("first_date must not be after last_date")
    query = urlencode(
        {
            "parameter": f"{station} ETOS",
            "syer": first.year,
            "smnth": first.month,
            "sdy": first.day,
            "eyer": last.year,
            "emnth": last.month,
            "edy": last.day,
        },
        quote_via=quote,
    )
    return f"{_ARCHIVE_URI}?{query}"


def parse_agrimet_etos_archive_response(
    response: str,
    *,
    station_id: str,
    latitude: float,
    longitude: float,
    elevation_m: float,
    retrieved_at: str,
    uri: str,
    source_version: str,
) -> ParsedAgriMetEtosArchive:
    """Parse one official archive response without filling missing ETos values."""
    station = _require_text(station_id, "station_id").upper()
    retrieval = _parse_utc(retrieved_at, "retrieved_at")
    location = (
        _finite(latitude, "latitude", -90.0, 90.0),
        _finite(longitude, "longitude", -180.0, 180.0),
        _finite(elevation_m, "elevation_m", -500.0, 10_000.0),
    )
    source_uri = _require_uri(uri)
    version = _require_text(source_version, "source_version")
    values, exclusions = _parse_agrimet_archive_values(response, station)
    rows = tuple(
        _archive_row(
            station,
            valid_date,
            etos_in,
            location,
            retrieval,
            source_uri,
            version,
        )
        for valid_date, etos_in in values
    )
    return _parsed_archive(rows, exclusions)


def parse_agrimet_etos_archive_response_with_station_history(
    response: str,
    *,
    station_id: str,
    station_history: AgriMetStationHistoryRegistry,
    retrieved_at: str,
    uri: str,
    source_version: str,
) -> ParsedAgriMetEtosArchive:
    """Parse ETos rows with a verified station location for each target day."""
    station = _require_text(station_id, "station_id").upper()
    retrieval = _parse_utc(retrieved_at, "retrieved_at")
    source_uri = _require_uri(uri)
    version = _require_text(source_version, "source_version")
    values, exclusions = _parse_agrimet_archive_values(response, station)
    rows = []
    for valid_date, etos_in in values:
        location = resolve_agrimet_station_location(
            station_history,
            station,
            valid_date,
        )
        rows.append(
            _archive_row(
                station,
                valid_date,
                etos_in,
                (location.latitude, location.longitude, location.elevation_m),
                retrieval,
                source_uri,
                version,
            )
        )
    return _parsed_archive(tuple(rows), exclusions)


def _parse_agrimet_archive_values(
    response: object,
    station: str,
) -> tuple[tuple[tuple[date, float], ...], tuple[date, ...]]:
    if not isinstance(response, str):
        raise ValueError("AgriMet archive response must be text")
    try:
        data = response.split("BEGIN DATA", 1)[1].split("END DATA", 1)[0]
    except IndexError as error:
        raise ValueError("AgriMet archive response must contain BEGIN DATA and END DATA") from error
    lines = [line.strip() for line in data.splitlines() if line.strip()]
    if not lines:
        raise ValueError("AgriMet archive response contains no data")
    header = [part.strip().upper() for part in lines[0].split(",")]
    if header != ["DATE", f"{station} ETOS"]:
        raise ValueError("AgriMet archive response header does not match station ETOS")
    values = []
    exclusions = []
    for line in lines[1:]:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2:
            raise ValueError("AgriMet archive response row must contain date and ETOS")
        valid_date = _parse_agrimet_archive_date(parts[0])
        if parts[1].lower() in {"", "m", "998877", "no record"}:
            exclusions.append(valid_date)
            continue
        try:
            etos_in = float(parts[1])
        except ValueError as error:
            raise ValueError("AgriMet archive ETOS must be numeric or a missing marker") from error
        values.append((valid_date, etos_in))
    return tuple(values), tuple(sorted(exclusions))


def _archive_row(
    station_id: str,
    valid_date: date,
    etos_in: float,
    location: tuple[float, float, float],
    retrieved_at: datetime,
    uri: str,
    source_version: str,
) -> dict[str, object]:
    return {
        "station_id": station_id,
        "latitude": location[0],
        "longitude": location[1],
        "elevation_m": location[2],
        "valid_date": valid_date.isoformat(),
        "etos_in": etos_in,
        "available_at": retrieved_at.isoformat().replace("+00:00", "Z"),
        "uri": uri,
        "source_version": source_version,
    }


def _parsed_archive(
    rows: tuple[dict[str, object], ...],
    exclusions: tuple[date, ...],
) -> ParsedAgriMetEtosArchive:
    return ParsedAgriMetEtosArchive(rows=rows, excluded_dates=exclusions)


def normalize_agrimet_etos_rows(
    rows: Iterable[dict[str, object]],
) -> tuple[AgriMetEtosObservation, ...]:
    """Convert strict AgriMet archive rows from inches per day to millimeters."""
    observations: list[AgriMetEtosObservation] = []
    seen: set[tuple[str, date]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"AgriMet row {index} must be an object")
        _require_exact_keys(
            row,
            {
                "station_id",
                "latitude",
                "longitude",
                "elevation_m",
                "valid_date",
                "etos_in",
                "available_at",
                "uri",
                "source_version",
            },
        )
        station_id = _require_text(row["station_id"], "station_id")
        valid_date = _parse_date(row["valid_date"], "valid_date")
        key = (station_id, valid_date)
        if key in seen:
            raise ValueError("AgriMet rows must not duplicate station_id and valid_date")
        seen.add(key)
        available_at = _parse_utc(row["available_at"], "available_at")
        if available_at <= idaho_local_day_end_utc(valid_date):
            raise ValueError("available_at must be after the Idaho local target day")
        observations.append(
            AgriMetEtosObservation(
                station_id=station_id,
                latitude=_finite(row["latitude"], "latitude", -90.0, 90.0),
                longitude=_finite(row["longitude"], "longitude", -180.0, 180.0),
                elevation_m=_finite(row["elevation_m"], "elevation_m", -500.0, 10_000.0),
                valid_date=valid_date,
                etos_mm=_finite(row["etos_in"], "etos_in", 0.0, math.inf)
                * _INCH_TO_MILLIMETER,
                available_at=available_at,
                uri=_require_uri(row["uri"]),
                source_version=_require_text(row["source_version"], "source_version"),
            )
        )
    return tuple(sorted(observations, key=lambda item: (item.station_id, item.valid_date)))


def materialize_agrimet_etos_artifact(source: Path, destination: Path) -> Path:
    """Write a checksum-bound normalized artifact from downloaded AgriMet rows."""
    source = Path(source)
    destination = Path(destination)
    try:
        raw_bytes = source.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot read AgriMet source rows: {source}") from error
    try:
        raw_rows = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("AgriMet source rows must be duplicate-key-free UTF-8 JSON") from error
    if not isinstance(raw_rows, list):
        raise ValueError("AgriMet source rows must be a JSON array")
    observations = normalize_agrimet_etos_rows(raw_rows)
    rows = [_artifact_row(observation) for observation in observations]
    normalized_bytes = _canonical_jsonl(rows)
    payload = {
        "artifact_type": _ARTIFACT_TYPE,
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "normalized_sha256": hashlib.sha256(normalized_bytes).hexdigest(),
        "rows": rows,
    }
    if destination.exists() or destination.is_symlink():
        raise ValueError("AgriMet artifact destination must not already exist")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError("AgriMet artifact destination parent must be a real directory")
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    with destination.open("xb") as handle:
        handle.write(encoded)
    return destination


def map_agrimet_station_to_grid(
    observation: AgriMetEtosObservation,
    grid_locations: dict[str, tuple[float, float]],
    *,
    maximum_distance_km: float,
) -> AgriMetGridMatch:
    """Match one station to its nearest forecast-grid point within a fixed limit."""
    if not isinstance(observation, AgriMetEtosObservation):
        raise ValueError("station-grid matching requires an AgriMetEtosObservation")
    if not grid_locations:
        raise ValueError("station-grid matching requires forecast-grid locations")
    maximum = _finite(maximum_distance_km, "maximum_distance_km", 0.0, math.inf)
    distances: list[tuple[float, str]] = []
    for grid_id, coordinates in grid_locations.items():
        if not isinstance(grid_id, str) or not grid_id.strip():
            raise ValueError("forecast grid_id must be non-empty text")
        if not isinstance(coordinates, tuple) or len(coordinates) != 2:
            raise ValueError("forecast grid location must be a latitude-longitude pair")
        latitude = _finite(coordinates[0], "forecast latitude", -90.0, 90.0)
        longitude = _finite(coordinates[1], "forecast longitude", -180.0, 180.0)
        distances.append(
            (
                _great_circle_distance_km(
                    observation.latitude, observation.longitude, latitude, longitude
                ),
                grid_id,
            )
        )
    distance_km, grid_id = min(distances, key=lambda item: (item[0], item[1]))
    if distance_km > maximum:
        raise ValueError("nearest forecast grid exceeds maximum_distance_km")
    return AgriMetGridMatch(
        station_id=observation.station_id,
        grid_id=grid_id,
        distance_km=distance_km,
    )


def _artifact_row(observation: AgriMetEtosObservation) -> dict[str, object]:
    return {
        "station_id": observation.station_id,
        "latitude": observation.latitude,
        "longitude": observation.longitude,
        "elevation_m": observation.elevation_m,
        "valid_date": observation.valid_date.isoformat(),
        "etos_mm": observation.etos_mm,
        "available_at": observation.available_at.isoformat().replace("+00:00", "Z"),
        "uri": observation.uri,
        "source_version": observation.source_version,
    }


def _canonical_jsonl(rows: list[dict[str, object]]) -> bytes:
    return "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        for row in rows
    ).encode("utf-8")


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _great_circle_distance_km(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    radius_km = 6_371.0088
    latitude_delta = math.radians(second_latitude - first_latitude)
    longitude_delta = math.radians(second_longitude - first_longitude)
    first_latitude_rad = math.radians(first_latitude)
    second_latitude_rad = math.radians(second_latitude)
    haversine = (
        math.sin(latitude_delta / 2.0) ** 2
        + math.cos(first_latitude_rad)
        * math.cos(second_latitude_rad)
        * math.sin(longitude_delta / 2.0) ** 2
    )
    return 2.0 * radius_km * math.asin(math.sqrt(haversine))


def _require_exact_keys(row: dict[str, object], expected: set[str]) -> None:
    if set(row) != expected:
        raise ValueError("AgriMet row fields must match the schema exactly")


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _finite(value: object, label: str, lower: float, upper: float) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or not lower <= result <= upper:
        raise ValueError(f"{label} is outside its valid range")
    return result


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


def _require_calendar_date(value: object, label: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{label} must be a calendar date")
    return value


def _parse_agrimet_archive_date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("AgriMet archive date must be MM/DD/YYYY")
    try:
        parsed = datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError as error:
        raise ValueError("AgriMet archive date must be MM/DD/YYYY") from error
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


def _require_uri(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("uri must be an absolute URI")
    parsed = urlparse(value)
    if not parsed.scheme or (parsed.scheme != "file" and not parsed.netloc):
        raise ValueError("uri must be an absolute URI")
    return value
