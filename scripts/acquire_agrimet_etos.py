#!/usr/bin/env python3
"""Acquire checksum-bound AgriMet ETos targets from a station-history registry."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import ssl
from typing import Optional
from urllib.request import Request, urlopen

import certifi

from mlet.sources.agrimet import (
    agrimet_etos_archive_uri,
    normalize_agrimet_etos_rows,
    parse_agrimet_etos_archive_response_with_station_history,
)
from mlet.sources.agrimet_station_history import (
    load_agrimet_station_history_registry,
)


_TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _date_arg(value: str) -> date:
    """Parse one explicit ISO calendar date."""
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


def main() -> int:
    """Write raw archive responses, parsed rows, exclusions, and a receipt."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--station-history", required=True, type=Path)
    parser.add_argument("--station", required=True, action="append")
    parser.add_argument("--first", required=True, type=_date_arg)
    parser.add_argument("--last", required=True, type=_date_arg)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--rows", required=True, type=Path)
    parser.add_argument("--exclusions", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    if args.first > args.last:
        parser.error("--first must not be after --last")
    registry = load_agrimet_station_history_registry(args.station_history)
    raw_root = _require_empty_real_directory(args.raw_root, "raw-root")
    _require_new_output(args.rows, "rows")
    _require_new_output(args.exclusions, "exclusions")
    _require_new_output(args.receipt, "receipt")

    rows = []
    exclusion_records = []
    receipt_objects = []
    stations = tuple(sorted({station.upper() for station in args.station}))
    for station in stations:
        try:
            locations = registry.locations_by_station[station]
        except KeyError as error:
            raise ValueError("requested station is absent from station history") from error
        for location in locations:
            first = max(args.first, location.valid_from)
            last = min(args.last, location.valid_to or args.last)
            if first > last:
                continue
            uri = agrimet_etos_archive_uri(station, first, last)
            response_bytes, headers = _download(uri)
            response_sha256 = hashlib.sha256(response_bytes).hexdigest()
            raw_path = raw_root / station / f"{first.isoformat()}_{last.isoformat()}.txt"
            if not raw_path.parent.exists():
                raw_path.parent.mkdir()
            _write_new(raw_path, response_bytes)
            retrieved_at = _format_utc(datetime.now(timezone.utc))
            parsed = parse_agrimet_etos_archive_response_with_station_history(
                response_bytes.decode("utf-8"),
                station_id=station,
                station_history=registry,
                retrieved_at=retrieved_at,
                uri=uri,
                source_version=f"sha256:{response_sha256}",
            )
            _require_interval_rows(parsed.rows, first, last)
            rows.extend(parsed.rows)
            exclusion_records.extend(
                {
                    "station_id": station,
                    "valid_date": excluded_date.isoformat(),
                    "reason": "published_missing_etos",
                    "uri": uri,
                    "source_version": f"sha256:{response_sha256}",
                }
                for excluded_date in parsed.excluded_dates
            )
            receipt_objects.append(
                {
                    "station_id": station,
                    "valid_from": first.isoformat(),
                    "valid_to": last.isoformat(),
                    "uri": uri,
                    "raw_path": raw_path.relative_to(raw_root).as_posix(),
                    "raw_sha256": response_sha256,
                    "byte_count": len(response_bytes),
                    "etag": headers.get("ETag"),
                    "last_modified": headers.get("Last-Modified"),
                    "retrieved_at": retrieved_at,
                }
            )
    normalize_agrimet_etos_rows(rows)
    _write_new(args.rows, _canonical_json_bytes(sorted(rows, key=_row_key)))
    _write_new(
        args.exclusions,
        _canonical_json_bytes(sorted(exclusion_records, key=_exclusion_key)),
    )
    _write_new(
        args.receipt,
        _canonical_json_bytes(
            {
                "schema_version": 1,
                "kind": "mlet.agrimet.etos-retrieval-receipt",
                "station_history_sha256": hashlib.sha256(
                    args.station_history.read_bytes()
                ).hexdigest(),
                "objects": receipt_objects,
            }
        ),
    )
    return 0


def _download(uri: str) -> tuple[bytes, dict[str, Optional[str]]]:
    request = Request(uri, headers={"User-Agent": "mlet-agrimet-etos/1"})
    with urlopen(request, timeout=60, context=_TLS_CONTEXT) as response:
        body = response.read()
        headers = {
            name: _optional_header(response.headers, name)
            for name in ("ETag", "Last-Modified")
        }
    if not body:
        raise ValueError("AgriMet archive response is empty")
    return body, headers


def _optional_header(headers: object, name: str) -> Optional[str]:
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None
    value = getter(name)
    return value if isinstance(value, str) and value else None


def _require_empty_real_directory(path: Path, label: str) -> Path:
    result = Path(path)
    if not result.is_dir() or result.is_symlink() or any(result.iterdir()):
        raise ValueError(f"{label} must be an existing empty real directory")
    return result


def _require_new_output(path: Path, label: str) -> None:
    result = Path(path)
    if result.exists() or result.is_symlink():
        raise ValueError(f"{label} destination must not already exist")
    if not result.parent.is_dir() or result.parent.is_symlink():
        raise ValueError(f"{label} parent must be a real directory")


def _require_interval_rows(rows: tuple[dict[str, object], ...], first: date, last: date) -> None:
    for row in rows:
        valid_date = date.fromisoformat(str(row["valid_date"]))
        if not first <= valid_date <= last:
            raise ValueError("AgriMet archive returned a target outside its request interval")


def _row_key(row: dict[str, object]) -> tuple[str, str]:
    return str(row["station_id"]), str(row["valid_date"])


def _exclusion_key(row: dict[str, object]) -> tuple[str, str]:
    return str(row["station_id"]), str(row["valid_date"])


def _write_new(path: Path, contents: bytes) -> None:
    with Path(path).open("xb") as handle:
        handle.write(contents)
    Path(path).chmod(0o444)


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
