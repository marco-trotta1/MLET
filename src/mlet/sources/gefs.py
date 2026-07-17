"""Import versioned GEFS daily artifacts without pretending to decode GRIB.

This module deliberately has no live NOAA transport.  A reproducible external
decoder must first produce the documented ``mlet.gefs.daily-artifact`` format
from a pinned GRIB input.  The importer then validates that canonical daily
artifact, caches the exact bytes it parsed, and atomically publishes its
normalized weather rows and a complete provenance receipt.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from mlet.outlook.contracts import WeatherMember


_ARTIFACT_TYPE = "mlet.gefs.daily-artifact"
_ARTIFACT_SCHEMA_VERSION = 1
_TRANSFORM = {
    "name": "noaa-gefs-grib-to-daily-asce-input",
    "version": "1",
}
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
    """Validate a complete 20-day canonical daily ensemble without imputation."""
    issued_datetime = _parse_utc_timestamp(issued_at, "issued_at")
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
    """Refuse live GEFS acquisition until a pinned GRIB decoder is available.

    This deliberately performs no HTTP request.  Use
    :func:`materialize_gefs_daily_artifact` only after an external, documented
    decoder has produced a canonical artifact with GRIB provenance.
    """
    del issue_date, idaho_bbox, destination
    raise NotImplementedError(
        "Live GEFS GRIB acquisition is disabled until a reproducible, versioned "
        "GRIB decoder and archived-artifact verification are added; import a "
        "mlet.gefs.daily-artifact instead."
    )


def materialize_gefs_daily_artifact(artifact_path: Path, destination: Path) -> Path:
    """Import one validated canonical daily artifact as a complete artifact set.

    The raw cache stores the exact canonical-artifact bytes passed to
    ``json.loads``.  The receipt is written last and records both that parsed
    byte hash and the immutable upstream GRIB hash supplied by the producer.
    """
    artifact_path = Path(artifact_path)
    try:
        raw_bytes = artifact_path.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot read GEFS daily artifact: {artifact_path}") from error
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("GEFS daily artifact must be UTF-8 JSON") from error

    provenance, rows, declared_normalized_sha256 = _validate_daily_artifact(payload)
    source_issue_at = _parse_utc_timestamp(
        provenance["source_issue_at"], "GEFS provenance source_issue_at"
    )
    bbox = _validate_idaho_bbox(provenance["idaho_bbox"])
    members = normalize_gefs_rows(rows, issued_at=_format_utc_timestamp(source_issue_at))
    for member in members:
        west, south, east, north = bbox
        if not (south <= member.latitude <= north and west <= member.longitude <= east):
            raise ValueError("GEFS daily artifact contains a weather cell outside the Idaho bbox")

    normalized_bytes = _normalized_bytes(members)
    normalized_sha256 = hashlib.sha256(normalized_bytes).hexdigest()
    if normalized_sha256 != declared_normalized_sha256:
        raise ValueError("GEFS daily artifact normalized_sha256 does not match rows")
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    destination = Path(destination)
    cache_path = (
        destination.parent
        / "data"
        / "cache"
        / f"gefs-canonical-{source_issue_at.date().isoformat()}-{raw_sha256[:16]}.json"
    )
    receipt_path = destination.with_suffix(f"{destination.suffix}.source.json")
    receipt = {
        "acquisition_mode": "imported_canonical_daily_artifact",
        "artifact_schema_version": _ARTIFACT_SCHEMA_VERSION,
        "artifact_type": _ARTIFACT_TYPE,
        "idaho_bbox": list(bbox),
        "name": "gefs",
        "normalized_sha256": normalized_sha256,
        "raw_sha256": raw_sha256,
        "source_issue_at": _format_utc_timestamp(source_issue_at),
        "transform": provenance["transform"],
        "upstream_raw_sha256": provenance["upstream_raw_sha256"],
        "uri": provenance["upstream_uri"],
        "variables": provenance["variables"],
    }
    _write_artifact_set(
        (
            (cache_path, raw_bytes),
            (destination, normalized_bytes),
            (receipt_path, _canonical_json_bytes(receipt)),
        )
    )
    return destination


def _validate_daily_artifact(
    payload: object,
) -> tuple[Mapping[str, object], list[dict[str, object]], str]:
    if not isinstance(payload, dict):
        raise ValueError("GEFS daily artifact must be a JSON object")
    if payload.get("artifact_type") != _ARTIFACT_TYPE:
        raise ValueError(f"GEFS daily artifact type must be {_ARTIFACT_TYPE!r}")
    if payload.get("schema_version") != _ARTIFACT_SCHEMA_VERSION:
        raise ValueError(
            f"GEFS daily artifact schema_version must be {_ARTIFACT_SCHEMA_VERSION}"
        )
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("GEFS daily artifact provenance must be an object")
    upstream_uri = provenance.get("upstream_uri")
    if not isinstance(upstream_uri, str) or not upstream_uri.startswith("https://"):
        raise ValueError("GEFS provenance upstream_uri must be an HTTPS URL")
    _parse_utc_timestamp(provenance.get("source_issue_at"), "GEFS provenance source_issue_at")
    _require_sha256(
        provenance.get("upstream_raw_sha256"), "GEFS provenance upstream_raw_sha256"
    )
    _validate_idaho_bbox(provenance.get("idaho_bbox"))
    variables = provenance.get("variables")
    if variables != sorted(_WEATHER_FIELDS):
        raise ValueError("GEFS provenance variables must be the six canonical weather fields")
    transform = provenance.get("transform")
    if transform != _TRANSFORM:
        raise ValueError("GEFS provenance transform must name the pinned daily transformation")
    rows = payload.get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("GEFS daily artifact rows must be an array of objects")
    normalized_sha256 = _require_sha256(
        payload.get("normalized_sha256"), "GEFS daily artifact normalized_sha256"
    )
    return provenance, rows, normalized_sha256


def _write_artifact_set(entries: tuple[tuple[Path, bytes], ...]) -> None:
    """Publish cache, normalized rows, and receipt as one rollback-capable set.

    Files are staged before any target changes.  The receipt is committed last;
    when any replace fails, every earlier target is restored (or removed when it
    was newly created), so a failed import cannot be mistaken for a completed
    receipt-backed acquisition.
    """
    targets = [path for path, _ in entries]
    if len(set(targets)) != len(targets):
        raise ValueError("GEFS artifact-set targets must be distinct")
    staged: dict[Path, Path] = {}
    originals: dict[Path, bytes | None] = {}
    committed: list[Path] = []
    try:
        for target, contents in entries:
            originals[target] = target.read_bytes() if target.exists() else None
            staged[target] = _stage_bytes(target, contents)
        for target, _ in entries:
            os.replace(staged[target], target)
            committed.append(target)
    except OSError:
        for target in reversed(committed):
            original = originals[target]
            if original is None:
                target.unlink(missing_ok=True)
            else:
                rollback = _stage_bytes(target, original)
                os.replace(rollback, target)
        raise
    finally:
        for temporary_path in staged.values():
            temporary_path.unlink(missing_ok=True)


def _stage_bytes(target: Path, contents: bytes) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=target.parent, prefix=f".{target.name}.", delete=False
    ) as handle:
        temporary_path = Path(handle.name)
        handle.write(contents)
        handle.flush()
        os.fsync(handle.fileno())
    return temporary_path


def _validate_idaho_bbox(value: object) -> tuple[float, float, float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise ValueError("idaho_bbox must be a (west, south, east, north) sequence")
    values = tuple(_finite_float(item, "idaho_bbox") for item in value)
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
        raise ValueError(f"GEFS row {row_index} field {name} is outside its unit-safe range")
    return value


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _parse_utc_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(
            f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z")
    return parsed.astimezone(timezone.utc)


def _format_utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("timestamps must be UTC")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")
    return value


def _normalized_bytes(members: Iterable[WeatherMember]) -> bytes:
    return "".join(
        json.dumps(_weather_member_payload(member), sort_keys=True, separators=(",", ":"))
        + "\n"
        for member in members
    ).encode("utf-8")


def _weather_member_payload(member: WeatherMember) -> dict[str, object]:
    payload = asdict(member)
    payload["issued_at"] = _format_utc_timestamp(member.issued_at)
    payload["valid_date"] = member.valid_date.isoformat()
    return payload


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
