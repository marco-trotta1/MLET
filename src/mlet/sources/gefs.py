"""Import versioned GEFS daily artifacts without pretending to decode GRIB.

This module deliberately has no live NOAA transport.  A reproducible external
decoder must first produce the documented ``mlet.gefs.daily-artifact`` format
from a pinned GRIB input.  The importer then validates that canonical daily
artifact, caches the exact bytes it parsed, and atomically publishes its
normalized weather rows and a complete provenance receipt.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import uuid

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
_CACHE_RELATIVE_DIRECTORY = Path("data") / "cache" / "gefs-daily-artifacts"
_GENERATION_PREFIX = "gefs-"
_RAW_FILENAME = "canonical-artifact.json"
_NORMALIZED_FILENAME = "weather_members.jsonl"
_RECEIPT_FILENAME = "receipt.json"


@dataclass(frozen=True)
class GefsDailyArtifactSet:
    """The three immutable files selected by one GEFS artifact pointer."""

    pointer_path: Path
    generation_id: str
    raw_path: Path
    normalized_path: Path
    receipt_path: Path


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


def materialize_gefs_daily_artifact(
    artifact_path: Path, artifact_pointer: Path
) -> GefsDailyArtifactSet:
    """Publish a complete immutable GEFS generation through one stable pointer.

    ``artifact_pointer`` is an atomically-replaced symlink, not a normalized
    JSONL output path.  Consumers must call :func:`resolve_gefs_daily_artifact`
    and use the resulting raw, normalized, and receipt paths as one set.
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

    artifact_pointer = Path(artifact_pointer)
    _require_safe_directory(artifact_pointer.parent, "GEFS artifact pointer parent")
    cache_directory = _prepare_cache_directory(artifact_pointer.parent)
    generation_id = (
        f"{_GENERATION_PREFIX}{source_issue_at.date().isoformat()}-{raw_sha256}"
    )
    receipt = {
        "acquisition_mode": "imported_canonical_daily_artifact",
        "artifact_schema_version": _ARTIFACT_SCHEMA_VERSION,
        "artifact_type": _ARTIFACT_TYPE,
        "generation_id": generation_id,
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
    _publish_generation(
        cache_directory,
        generation_id,
        raw_bytes,
        normalized_bytes,
        _canonical_json_bytes(receipt),
    )
    _publish_pointer(artifact_pointer, generation_id)
    return resolve_gefs_daily_artifact(artifact_pointer)


def resolve_gefs_daily_artifact(artifact_pointer: Path) -> GefsDailyArtifactSet:
    """Resolve and validate one complete immutable GEFS artifact generation.

    The pointer may name only a generation directly beneath this pointer's
    ``data/cache/gefs-daily-artifacts`` directory.  That restriction prevents
    a supplied symlink from selecting arbitrary filesystem content.
    """
    artifact_pointer = Path(artifact_pointer)
    _require_safe_directory(artifact_pointer.parent, "GEFS artifact pointer parent")
    if not artifact_pointer.is_symlink():
        raise ValueError("GEFS artifact pointer must be a symlink to a complete generation")

    target = Path(os.readlink(artifact_pointer))
    if target.is_absolute() or target.parent != _CACHE_RELATIVE_DIRECTORY:
        raise ValueError("GEFS artifact pointer has an unsafe generation target")
    generation_id = target.name
    if not _is_generation_id(generation_id):
        raise ValueError("GEFS artifact pointer has an invalid generation identifier")

    generation_directory = artifact_pointer.parent / target
    _require_safe_directory(generation_directory, "GEFS artifact generation")
    artifact_set = GefsDailyArtifactSet(
        pointer_path=artifact_pointer,
        generation_id=generation_id,
        raw_path=generation_directory / _RAW_FILENAME,
        normalized_path=generation_directory / _NORMALIZED_FILENAME,
        receipt_path=generation_directory / _RECEIPT_FILENAME,
    )
    _validate_resolved_generation(artifact_set)
    return artifact_set


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


def _prepare_cache_directory(pointer_parent: Path) -> Path:
    """Create the controlled cache directory without accepting symlink roots."""
    cache_directory = pointer_parent / _CACHE_RELATIVE_DIRECTORY
    _reject_symlink_ancestors(cache_directory)
    cache_directory.mkdir(parents=True, exist_ok=True)
    _require_safe_directory(cache_directory, "GEFS cache directory")
    return cache_directory


def _publish_generation(
    cache_directory: Path,
    generation_id: str,
    raw_bytes: bytes,
    normalized_bytes: bytes,
    receipt_bytes: bytes,
) -> None:
    """Stage, fsync, and atomically publish one immutable generation directory."""
    generation_directory = cache_directory / generation_id
    if generation_directory.exists() or generation_directory.is_symlink():
        _validate_existing_generation(
            generation_directory,
            generation_id,
            raw_bytes,
            normalized_bytes,
            receipt_bytes,
        )
        return

    staging_directory = Path(
        tempfile.mkdtemp(prefix=f".{generation_id}.", dir=cache_directory)
    )
    published = False
    try:
        _write_new_file(staging_directory / _RAW_FILENAME, raw_bytes)
        _write_new_file(staging_directory / _NORMALIZED_FILENAME, normalized_bytes)
        _write_new_file(staging_directory / _RECEIPT_FILENAME, receipt_bytes)
        os.chmod(staging_directory, 0o555)
        _fsync_directory(staging_directory)
        try:
            os.replace(staging_directory, generation_directory)
            published = True
            _fsync_directory(cache_directory)
        except FileExistsError:
            _validate_existing_generation(
                generation_directory,
                generation_id,
                raw_bytes,
                normalized_bytes,
                receipt_bytes,
            )
    finally:
        if not published and staging_directory.exists():
            _remove_staging_generation(staging_directory)


def _validate_existing_generation(
    generation_directory: Path,
    generation_id: str,
    raw_bytes: bytes,
    normalized_bytes: bytes,
    receipt_bytes: bytes,
) -> None:
    """Refuse to overwrite a content-addressed generation with different bytes."""
    _require_safe_directory(generation_directory, "GEFS artifact generation")
    expected = {
        _RAW_FILENAME: raw_bytes,
        _NORMALIZED_FILENAME: normalized_bytes,
        _RECEIPT_FILENAME: receipt_bytes,
    }
    for filename, contents in expected.items():
        path = generation_directory / filename
        if _read_regular_file(path, f"GEFS generation {filename}") != contents:
            raise ValueError(
                f"GEFS generation {generation_id!r} exists with different immutable content"
            )


def _publish_pointer(artifact_pointer: Path, generation_id: str) -> None:
    """Atomically switch the sole public pointer after its generation is complete."""
    _require_safe_directory(artifact_pointer.parent, "GEFS artifact pointer parent")
    relative_target = _CACHE_RELATIVE_DIRECTORY / generation_id
    temporary_pointer = artifact_pointer.parent / (
        f".{artifact_pointer.name}.{uuid.uuid4().hex}.next"
    )
    created_pointer = False
    try:
        os.symlink(relative_target, temporary_pointer)
        created_pointer = True
        os.replace(temporary_pointer, artifact_pointer)
        _fsync_directory(artifact_pointer.parent)
    finally:
        if created_pointer and temporary_pointer.is_symlink():
            temporary_pointer.unlink()


def _validate_resolved_generation(artifact_set: GefsDailyArtifactSet) -> None:
    raw_bytes = _read_regular_file(artifact_set.raw_path, "GEFS raw artifact")
    normalized_bytes = _read_regular_file(
        artifact_set.normalized_path, "GEFS normalized weather rows"
    )
    receipt_bytes = _read_regular_file(artifact_set.receipt_path, "GEFS source receipt")
    try:
        receipt = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("GEFS source receipt must be UTF-8 JSON") from error
    if not isinstance(receipt, dict):
        raise ValueError("GEFS source receipt must be an object")
    if receipt.get("artifact_type") != _ARTIFACT_TYPE:
        raise ValueError("GEFS source receipt artifact_type is invalid")
    if receipt.get("artifact_schema_version") != _ARTIFACT_SCHEMA_VERSION:
        raise ValueError("GEFS source receipt schema version is invalid")
    if receipt.get("generation_id") != artifact_set.generation_id:
        raise ValueError("GEFS source receipt generation_id does not match its pointer")
    if receipt.get("raw_sha256") != hashlib.sha256(raw_bytes).hexdigest():
        raise ValueError("GEFS source receipt raw_sha256 does not match cached bytes")
    if receipt.get("normalized_sha256") != hashlib.sha256(normalized_bytes).hexdigest():
        raise ValueError("GEFS source receipt normalized_sha256 does not match rows")


def _write_new_file(path: Path, contents: bytes) -> None:
    """Write a staged regular file without following an unexpected symlink."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    os.chmod(path, 0o444)


def _read_regular_file(path: Path, label: str) -> bytes:
    """Read a regular artifact member without accepting a symlink file."""
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError(f"cannot read {label}") from error
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"{label} must be a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(descriptor)


def _fsync_directory(directory: Path) -> None:
    """Persist a directory entry before the next atomic publication step."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_staging_generation(staging_directory: Path) -> None:
    """Remove only the known files from an unpublished, private staging directory."""
    if staging_directory.is_symlink():
        raise ValueError("GEFS staging directory must not be a symlink")
    os.chmod(staging_directory, 0o700)
    for filename in (_RAW_FILENAME, _NORMALIZED_FILENAME, _RECEIPT_FILENAME):
        path = staging_directory / filename
        if path.exists() or path.is_symlink():
            if path.is_symlink():
                raise ValueError("GEFS staging member must not be a symlink")
            path.unlink()
    staging_directory.rmdir()


def _reject_symlink_ancestors(path: Path) -> None:
    """Reject known symlink path components before any GEFS write path is used."""
    candidate = path
    while candidate != candidate.parent:
        if candidate.is_symlink():
            raise ValueError(f"GEFS artifact path must not traverse symlinks: {candidate}")
        candidate = candidate.parent


def _require_safe_directory(path: Path, label: str) -> None:
    _reject_symlink_ancestors(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} must be a non-symlink directory")


def _is_generation_id(value: str) -> bool:
    prefix, separator, digest = value.rpartition("-")
    return (
        separator == "-"
        and prefix.startswith(_GENERATION_PREFIX)
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )


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
