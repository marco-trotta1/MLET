"""Normalize bounded GEFS daily weather rows into the outlook contract.

The downloader deliberately accepts only the project's canonical daily-row
response.  Decoding NOAA GRIB is a separate acquisition concern; keeping it
outside this module prevents a source-specific binary format from leaking into
the ETo core.  The normalized JSONL and its source receipt are suitable for a
live acquisition, an archive replay, or a conspicuously non-scientific fixture.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Mapping

import requests

from mlet.outlook.contracts import WeatherMember


_GEFS_DAILY_URL = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gefs_atmos_0p50a.pl"
_WEATHER_FIELDS = frozenset(
    {
        "tmax_c",
        "tmin_c",
        "vapor_pressure_kpa",
        "wind_m_s",
        "solar_mj_m2_day",
        "precip_mm",
    }
)
_ROW_FIELDS = frozenset(
    {
        "grid_id",
        "latitude",
        "longitude",
        "elevation_m",
        "member_id",
        "valid_date",
        *_WEATHER_FIELDS,
    }
)
_IDAHO_EXTENT = (-118.0, 41.0, -110.0, 50.0)


def normalize_gefs_rows(
    rows: Iterable[dict[str, object]], issued_at: str
) -> list[WeatherMember]:
    """Validate a complete 20-day GEFS daily ensemble without imputation.

    A valid source has one and only one row for every
    ``(grid_id, member_id, valid_date)`` and exactly the lead-day-1 through
    lead-day-20 dates for each grid/member pair.  The required meteorological
    fields are supplied in the units named by the source registry.
    """
    issued_datetime = _parse_utc_timestamp(issued_at)
    issue_date = issued_datetime.date()
    expected_dates = {issue_date + timedelta(days=lead) for lead in range(1, 21)}
    members: list[WeatherMember] = []
    seen_keys: set[tuple[str, str, date]] = set()
    dates_by_member: dict[tuple[str, str], set[date]] = {}

    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"GEFS row {row_index} must be an object")
        missing = sorted(_ROW_FIELDS - set(row))
        if missing:
            raise ValueError(
                f"GEFS row {row_index} is missing required fields: {', '.join(missing)}"
            )

        grid_id = _require_text(row, "grid_id", row_index)
        member_id = _require_text(row, "member_id", row_index)
        valid_date = _require_date(row, "valid_date", row_index)
        key = (grid_id, member_id, valid_date)
        if key in seen_keys:
            raise ValueError(
                "GEFS contains a duplicate (grid_id, member_id, valid_date) row"
            )
        seen_keys.add(key)

        latitude = _require_number(row, "latitude", row_index, -90.0, 90.0)
        longitude = _require_number(row, "longitude", row_index, -180.0, 180.0)
        elevation_m = _require_number(row, "elevation_m", row_index, -500.0, 10_000.0)
        tmax_c = _require_number(row, "tmax_c", row_index, -90.0, 70.0)
        tmin_c = _require_number(row, "tmin_c", row_index, -90.0, 70.0)
        if tmax_c < tmin_c:
            raise ValueError(f"GEFS row {row_index} has tmax_c below tmin_c")
        vapor_pressure_kpa = _require_number(
            row, "vapor_pressure_kpa", row_index, 0.0, 15.0
        )
        wind_m_s = _require_number(row, "wind_m_s", row_index, 0.0, 100.0)
        solar_mj_m2_day = _require_number(
            row, "solar_mj_m2_day", row_index, 0.0, 60.0
        )
        precip_mm = _require_number(row, "precip_mm", row_index, 0.0, 1_000.0)
        members.append(
            WeatherMember(
                grid_id=grid_id,
                latitude=latitude,
                longitude=longitude,
                elevation_m=elevation_m,
                member_id=member_id,
                issued_at=issued_datetime,
                valid_date=valid_date,
                tmax_c=tmax_c,
                tmin_c=tmin_c,
                vapor_pressure_kpa=vapor_pressure_kpa,
                wind_m_s=wind_m_s,
                solar_mj_m2_day=solar_mj_m2_day,
                precip_mm=precip_mm,
            )
        )
        dates_by_member.setdefault((grid_id, member_id), set()).add(valid_date)

    if not members:
        raise ValueError("GEFS source contains no weather rows")
    for (grid_id, member_id), valid_dates in sorted(dates_by_member.items()):
        if valid_dates != expected_dates:
            raise ValueError(
                "GEFS must contain exactly 20 daily leads (lead days 1 through 20) "
                f"for grid {grid_id!r}, member {member_id!r}"
            )
    return sorted(members, key=lambda item: (item.grid_id, item.member_id, item.valid_date))


def fetch_gefs(
    issue_date: date,
    idaho_bbox: tuple[float, float, float, float],
    destination: Path,
) -> Path:
    """Fetch, validate, and atomically materialize bounded normalized GEFS rows.

    ``idaho_bbox`` is ``(west, south, east, north)`` in WGS84 degrees.  This
    function requests only the six registry weather variables.  It writes the
    source response beneath ``data/cache`` and a checksum-addressable source
    receipt alongside ``destination`` only after all rows pass completeness and
    bounds checks.
    """
    if not isinstance(issue_date, date) or isinstance(issue_date, datetime):
        raise ValueError("issue_date must be a date")
    west, south, east, north = _validate_idaho_bbox(idaho_bbox)
    required_variables = _registry_weather_variables()
    issued_at = datetime.combine(issue_date, datetime.min.time(), tzinfo=timezone.utc)
    issued_at_text = _format_utc_timestamp(issued_at)
    parameters: dict[str, object] = {
        "bottomlat": south,
        "issue_date": issue_date.isoformat(),
        "leftlon": west,
        "rightlon": east,
        "toplat": north,
        "variables": ",".join(required_variables),
    }
    response = requests.get(_GEFS_DAILY_URL, params=parameters, timeout=60)
    response.raise_for_status()
    try:
        payload = response.json()
    except (TypeError, ValueError) as error:
        raise ValueError("GEFS response must be a canonical JSON array of daily rows") from error
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ValueError("GEFS response must be a canonical JSON array of daily rows")

    rows: list[dict[str, object]] = payload
    members = normalize_gefs_rows(rows, issued_at=issued_at_text)
    for member in members:
        if not (south <= member.latitude <= north and west <= member.longitude <= east):
            raise ValueError("GEFS response contains a weather cell outside the Idaho bbox")

    raw_bytes = response.content
    if not isinstance(raw_bytes, bytes):
        raise ValueError("GEFS response content must be bytes")
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    cache_path = Path("data") / "cache" / f"gefs-{issue_date.isoformat()}-{raw_sha256[:16]}.json"
    retrieved_at = _format_utc_timestamp(datetime.now(timezone.utc))
    receipt = {
        "name": "gefs",
        "uri": str(getattr(response, "url", _GEFS_DAILY_URL)),
        "retrieved_at": retrieved_at,
        "sha256": raw_sha256,
        "observed_through": None,
        "source_issue_at": issued_at_text,
        "idaho_bbox": [west, south, east, north],
        "required_variables": required_variables,
    }
    normalized_text = "".join(
        json.dumps(_weather_member_payload(member), sort_keys=True, separators=(",", ":"))
        + "\n"
        for member in members
    )

    destination = Path(destination)
    receipt_path = destination.with_suffix(f"{destination.suffix}.source.json")
    _write_transactionally(cache_path, raw_bytes)
    _write_transactionally(receipt_path, _canonical_json_bytes(receipt))
    _write_transactionally(destination, normalized_text.encode("utf-8"))
    return destination


def _registry_weather_variables() -> list[str]:
    registry_path = Path(__file__).resolve().parents[3] / "data" / "outlook" / "source_registry.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        required = registry["sources"]["gefs"]["required_variables"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("the GEFS source registry is unavailable or malformed") from error
    if not isinstance(required, list) or set(required) != _WEATHER_FIELDS:
        raise ValueError("the GEFS source registry must define exactly the required weather variables")
    if any(not isinstance(variable, str) for variable in required):
        raise ValueError("the GEFS source registry variables must be strings")
    return sorted(required)


def _validate_idaho_bbox(
    bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if not isinstance(bbox, tuple) or len(bbox) != 4:
        raise ValueError("idaho_bbox must be a (west, south, east, north) tuple")
    values = tuple(_finite_float(item, "idaho_bbox") for item in bbox)
    west, south, east, north = values
    idaho_west, idaho_south, idaho_east, idaho_north = _IDAHO_EXTENT
    if not (
        idaho_west <= west < east <= idaho_east
        and idaho_south <= south < north <= idaho_north
    ):
        raise ValueError("idaho_bbox must be a non-empty WGS84 extent within Idaho")
    return west, south, east, north


def _require_text(row: Mapping[str, object], name: str, row_index: int) -> str:
    value = row[name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"GEFS row {row_index} field {name} must be non-empty text")
    return value.strip()


def _require_date(row: Mapping[str, object], name: str, row_index: int) -> date:
    value = row[name]
    if not isinstance(value, str):
        raise ValueError(f"GEFS row {row_index} field {name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"GEFS row {row_index} field {name} must be YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise ValueError(f"GEFS row {row_index} field {name} must be YYYY-MM-DD")
    return parsed


def _require_number(
    row: Mapping[str, object], name: str, row_index: int, minimum: float, maximum: float
) -> float:
    value = _finite_float(row[name], f"GEFS row {row_index} field {name}")
    if not minimum <= value <= maximum:
        raise ValueError(
            f"GEFS row {row_index} field {name} is outside its unit-safe range"
        )
    return value


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _parse_utc_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("issued_at must be an explicit UTC ISO-8601 timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError("issued_at must be an explicit UTC ISO-8601 timestamp ending in Z") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("issued_at must be an explicit UTC ISO-8601 timestamp ending in Z")
    return parsed.astimezone(timezone.utc)


def _format_utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("timestamps must be UTC")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _weather_member_payload(member: WeatherMember) -> dict[str, object]:
    payload = asdict(member)
    payload["issued_at"] = _format_utc_timestamp(member.issued_at)
    payload["valid_date"] = member.valid_date.isoformat()
    return payload


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _write_transactionally(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
