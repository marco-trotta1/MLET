"""Retrieve a fixed GEFSv12 raw-object plan with immutable receipts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import certifi
import hashlib
import json
import math
import os
from pathlib import Path
import ssl
import tempfile
from typing import Any, Optional
from urllib.request import Request, urlopen

from mlet.sources.gefs_reforecast_plan import build_gefs_reforecast_acquisition_plan

_CHUNK_BYTES = 1024 * 1024
_PLAN_OBJECT_FIELDS = {
    "issue_time",
    "member_id",
    "component",
    "horizon_segment",
    "uri",
    "local_path",
}
_RECEIPT_OBJECT_FIELDS = _PLAN_OBJECT_FIELDS | {
    "byte_count",
    "sha256",
    "etag",
    "last_modified",
    "retrieved_at",
}
_TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())


@dataclass(frozen=True)
class GefsReforecastRawObject:
    """One local raw GRIB object verified against its retrieval receipt."""

    issue_time: datetime
    member_id: str
    component: str
    horizon_segment: str
    uri: str
    path: Path
    sha256: str


def retrieve_gefs_reforecast_plan(
    plan: Mapping[str, object],
    *,
    data_root: Path,
    receipt_path: Path,
    retrieved_at: datetime,
    opener: Optional[Callable[[Request], Any]] = None,
    max_workers: int = 1,
    timeout_seconds: float = 600.0,
) -> Path:
    """Retrieve every planned object once and write its checksum receipt.

    The function accepts only a plan reconstructed by
    `build_gefs_reforecast_acquisition_plan()`. It does not replace raw files
    or an existing receipt. A failed run leaves completed immutable files in
    place, so a caller must prepare a new empty archive root for another run.
    """
    objects = _validated_plan_objects(plan)
    if type(max_workers) is not int or not 1 <= max_workers <= 16:
        raise ValueError("GEFS max_workers must be an integer from 1 through 16")
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds):
        raise ValueError("GEFS timeout_seconds must be finite")
    if not 1.0 <= float(timeout_seconds) <= 3_600.0:
        raise ValueError("GEFS timeout_seconds must be from 1 through 3600")
    retrieval_time = _require_utc(retrieved_at, "retrieved_at")
    data_root_path = Path(data_root)
    if data_root_path.is_symlink():
        raise ValueError("GEFS data_root must not be a symlink")
    data_root_path.mkdir(parents=True, exist_ok=True)
    root = data_root_path.resolve(strict=True)
    receipt = Path(receipt_path)
    if receipt.exists() or receipt.is_symlink():
        raise ValueError("GEFS retrieval receipt path must not already exist")
    if not receipt.parent.is_dir() or receipt.parent.is_symlink():
        raise ValueError("GEFS retrieval receipt parent must be a real directory")

    def retrieve_object(object_plan: Mapping[str, str]) -> dict[str, object]:
        local_path = _require_text(object_plan["local_path"], "GEFS local_path")
        destination = _new_destination(root, local_path)
        return _retrieve_one(
            _require_text(object_plan["uri"], "GEFS URI"),
            destination,
            opener=opener,
            timeout_seconds=float(timeout_seconds),
        )

    if max_workers == 1:
        metadata_values = [retrieve_object(object_plan) for object_plan in objects]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            metadata_values = list(executor.map(retrieve_object, objects))

    receipt_objects = []
    for object_plan, metadata in zip(objects, metadata_values):
        receipt_objects.append(
            {
                **object_plan,
                "byte_count": metadata["byte_count"],
                "sha256": metadata["sha256"],
                "etag": metadata["etag"],
                "last_modified": metadata["last_modified"],
                "retrieved_at": _format_utc(retrieval_time),
            }
        )
    payload = {
        "schema_version": 1,
        "kind": "mlet.gefs.reforecast-retrieval-receipt",
        "objects": receipt_objects,
    }
    _write_new(receipt, _canonical_json_bytes(payload))
    return receipt


def load_verified_gefs_reforecast_receipt(
    receipt_path: Path,
    *,
    data_root: Path,
) -> tuple[GefsReforecastRawObject, ...]:
    """Load a complete receipt and re-hash every referenced local raw object."""
    try:
        payload = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("GEFS retrieval receipt must be readable UTF-8 JSON") from error
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "kind", "objects"}:
        raise ValueError("GEFS retrieval receipt fields must match the schema exactly")
    if payload["schema_version"] != 1 or payload["kind"] != "mlet.gefs.reforecast-retrieval-receipt":
        raise ValueError("GEFS retrieval receipt has an unsupported schema")
    raw_objects = payload["objects"]
    if not isinstance(raw_objects, list) or not raw_objects:
        raise ValueError("GEFS retrieval receipt objects must be a non-empty list")
    plan = {
        "schema_version": 1,
        "kind": "mlet.gefs.reforecast-acquisition-plan",
        "objects": [{key: value.get(key) for key in _PLAN_OBJECT_FIELDS} for value in raw_objects if isinstance(value, dict)],
    }
    plan_objects = _validated_plan_objects(plan)
    if len(plan_objects) != len(raw_objects):
        raise ValueError("GEFS retrieval receipt objects must be JSON objects")
    data_root_path = Path(data_root)
    if data_root_path.is_symlink():
        raise ValueError("GEFS receipt data_root must not be a symlink")
    root = data_root_path.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("GEFS receipt data_root must be a real directory")
    verified = []
    for receipt_object, plan_object in zip(raw_objects, plan_objects):
        if not isinstance(receipt_object, dict) or set(receipt_object) != _RECEIPT_OBJECT_FIELDS:
            raise ValueError("GEFS retrieval receipt object fields must match the schema exactly")
        if {key: receipt_object[key] for key in _PLAN_OBJECT_FIELDS} != plan_object:
            raise ValueError("GEFS retrieval receipt object does not match the fixed plan")
        _require_sha256(receipt_object["sha256"])
        if type(receipt_object["byte_count"]) is not int or receipt_object["byte_count"] < 1:
            raise ValueError("GEFS retrieval receipt byte_count must be a positive integer")
        _require_utc(_parse_utc(_require_text(receipt_object["retrieved_at"], "retrieved_at")), "retrieved_at")
        if any(
            receipt_object[field] is not None and not isinstance(receipt_object[field], str)
            for field in ("etag", "last_modified")
        ):
            raise ValueError("GEFS retrieval receipt response metadata must be text or null")
        path = _existing_destination(root, plan_object["local_path"])
        if path.stat().st_size != receipt_object["byte_count"]:
            raise ValueError("GEFS raw file byte count does not match its receipt")
        if _sha256_file(path) != receipt_object["sha256"]:
            raise ValueError("GEFS raw file SHA-256 does not match its receipt")
        verified.append(
            GefsReforecastRawObject(
                issue_time=_parse_utc(plan_object["issue_time"]),
                member_id=plan_object["member_id"],
                component=plan_object["component"],
                horizon_segment=plan_object["horizon_segment"],
                uri=plan_object["uri"],
                path=path,
                sha256=receipt_object["sha256"],
            )
        )
    return tuple(verified)


def _validated_plan_objects(plan: Mapping[str, object]) -> list[dict[str, str]]:
    if not isinstance(plan, Mapping) or set(plan) != {"schema_version", "kind", "objects"}:
        raise ValueError("GEFS acquisition plan fields must match the schema exactly")
    if plan["schema_version"] != 1 or plan["kind"] != "mlet.gefs.reforecast-acquisition-plan":
        raise ValueError("GEFS acquisition plan has an unsupported schema")
    raw_objects = plan["objects"]
    if not isinstance(raw_objects, list) or not raw_objects:
        raise ValueError("GEFS acquisition plan objects must be a non-empty list")
    required = _PLAN_OBJECT_FIELDS
    objects: list[dict[str, str]] = []
    for value in raw_objects:
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("GEFS acquisition plan object fields must match the schema exactly")
        object_plan = {key: _require_text(value[key], f"GEFS {key}") for key in required}
        objects.append(object_plan)
    issue_times = tuple(
        sorted({_parse_utc(object_plan["issue_time"]) for object_plan in objects})
    )
    expected = build_gefs_reforecast_acquisition_plan(issue_times)
    if _canonical_json_bytes(plan) != _canonical_json_bytes(expected):
        raise ValueError("GEFS acquisition plan does not match the frozen source layout")
    return objects


def _retrieve_one(
    uri: str,
    destination: Path,
    *,
    opener: Optional[Callable[[Request], Any]],
    timeout_seconds: float,
) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(uri, headers={"User-Agent": "mlet-gefs-reforecast/1"})
    response = (
        urlopen(request, timeout=timeout_seconds, context=_TLS_CONTEXT)
        if opener is None
        else opener(request)
    )
    digest = hashlib.sha256()
    byte_count = 0
    temporary_name: Optional[str] = None
    try:
        with response, tempfile.NamedTemporaryFile(
            mode="xb", dir=destination.parent, prefix=".gefs-", suffix=".part", delete=False
        ) as temporary:
            temporary_name = temporary.name
            while chunk := response.read(_CHUNK_BYTES):
                if not isinstance(chunk, bytes):
                    raise ValueError("GEFS response body must yield bytes")
                temporary.write(chunk)
                digest.update(chunk)
                byte_count += len(chunk)
        if byte_count == 0:
            raise ValueError("GEFS response body is empty")
        try:
            os.link(temporary_name, destination)
        except FileExistsError as error:
            raise ValueError("GEFS raw destination must not already exist") from error
        os.chmod(destination, 0o444)
        os.unlink(temporary_name)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    headers = getattr(response, "headers", {})
    return {
        "byte_count": byte_count,
        "sha256": digest.hexdigest(),
        "etag": _optional_header(headers, "ETag"),
        "last_modified": _optional_header(headers, "Last-Modified"),
    }


def _new_destination(root: Path, local_path: str) -> Path:
    relative = Path(local_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("GEFS local_path must remain below data_root")
    destination = root / relative
    if destination.exists() or destination.is_symlink():
        raise ValueError("GEFS raw destination must not already exist")
    return destination


def _existing_destination(root: Path, local_path: str) -> Path:
    relative = Path(local_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("GEFS local_path must remain below data_root")
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise ValueError("GEFS receipt raw path must name a regular file")
    return path


def _write_new(path: Path, contents: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(contents)
    path.chmod(0o444)


def _optional_header(headers: object, name: str) -> Optional[str]:
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None
    value = getter(name)
    return value if isinstance(value, str) and value else None


def _parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("GEFS issue_time must be strict UTC ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("GEFS issue_time must be strict UTC ISO-8601 text") from error
    return _require_utc(parsed, "GEFS issue_time")


def _require_utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be explicit UTC")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{label} must be explicit UTC")
    return value.astimezone(timezone.utc)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value


def _require_sha256(value: object) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("GEFS retrieval receipt SHA-256 must be lowercase hexadecimal")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError("GEFS retrieval receipt SHA-256 must be lowercase hexadecimal")


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()
