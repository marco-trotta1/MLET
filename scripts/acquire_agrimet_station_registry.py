#!/usr/bin/env python3
"""Download and normalize the public USBR AgriMet station registry."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
import ssl

import certifi


JSON_URI = "https://www.usbr.gov/pn/agrimet/agrimetmap/usbr_map.json"
CSV_URI = "https://www.usbr.gov/pn/agrimet/location.csv"
NEWS_URI = "https://www.usbr.gov/pn/agrimet/news.html"
STATION_PAGE = "https://www.usbr.gov/pn/agrimet/agrimetmap/site.html?redirect_url="


def main() -> int:
    """Write one immutable current snapshot and retain source checksums."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--history-first", default="2013-01-01", type=_date_arg)
    parser.add_argument("--history-last", default="2019-12-31", type=_date_arg)
    parser.add_argument("--raw-root", type=Path)
    args = parser.parse_args()
    if args.history_first > args.history_last:
        parser.error("--history-first must not be after --history-last")
    if args.destination.exists() or args.destination.is_symlink():
        raise ValueError("registry destination must not already exist")
    if not args.destination.parent.is_dir() or args.destination.parent.is_symlink():
        raise ValueError("registry destination parent must be a real directory")
    raw = {
        "json": _download(JSON_URI),
        "csv": _download(CSV_URI),
        "news": _download(NEWS_URI),
    }
    features = _parse_json_features(raw["json"])
    csv_ids = _parse_csv_ids(raw["csv"])
    feature_ids = {str(feature["properties"]["siteid"]).upper() for feature in features}
    if not csv_ids.issubset(feature_ids):
        raise ValueError("USBR CSV contains station IDs absent from the JSON registry")
    retrieved_at = _format_utc(datetime.now(timezone.utc))
    payload = {
        "schema_version": 1,
        "kind": "mlet.agrimet.station-registry",
        "source_snapshot": {
            "json_uri": JSON_URI,
            "json_sha256": _sha256(raw["json"]),
            "csv_uri": CSV_URI,
            "csv_sha256": _sha256(raw["csv"]),
            "news_uri": NEWS_URI,
            "news_sha256": _sha256(raw["news"]),
            "retrieved_at": retrieved_at,
        },
        "history_window": {
            "first": args.history_first.isoformat(),
            "last": args.history_last.isoformat(),
        },
        "stations": [
            _normalize_feature(feature)
            for feature in sorted(features, key=lambda item: str(item["properties"]["siteid"]).upper())
        ],
    }
    _write_new(args.destination, _canonical_json(payload))
    if args.raw_root is not None:
        _write_raw_sources(args.raw_root, raw)
    idaho = [station for station in payload["stations"] if station["state"] == "ID"]
    missing_install = sum(station["installation_date"] is None for station in idaho)
    print(f"stations: {len(payload['stations'])}")
    print(f"csv_stations: {len(csv_ids)}")
    print(f"json_only_stations: {len(feature_ids - csv_ids)}")
    print(f"idaho_stations: {len(idaho)}")
    print(f"idaho_missing_installation_dates: {missing_install}")
    print(f"retrieved_at: {retrieved_at}")
    print(f"destination: {args.destination}")
    return 0


def _date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


def _download(uri: str) -> bytes:
    request = Request(uri, headers={"User-Agent": "mlet-agrimet-registry/1"})
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, context=context, timeout=60) as response:  # noqa: S310
        body = response.read()
    if not body:
        raise ValueError(f"USBR source response is empty: {uri}")
    return body


def _parse_json_features(contents: bytes) -> list[dict[str, object]]:
    try:
        payload = json.loads(contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("USBR station JSON must be UTF-8 JSON") from error
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("USBR station JSON must be a FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("USBR station JSON must contain features")
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError("USBR station feature must be an object")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            raise ValueError("USBR station feature must contain properties and geometry")
        coordinates = geometry.get("coordinates")
        if geometry.get("type") != "Point" or not isinstance(coordinates, list) or len(coordinates) != 2:
            raise ValueError("USBR station geometry must be a point")
        if not isinstance(properties.get("siteid"), str) or not properties["siteid"].strip():
            raise ValueError("USBR station feature must contain siteid")
    return [feature for feature in features if isinstance(feature, dict)]


def _parse_csv_ids(contents: bytes) -> set[str]:
    text = contents.decode("utf-8-sig")
    lines = text.splitlines()
    try:
        header_index = next(index for index, line in enumerate(lines) if line.lower().startswith("siteid,"))
    except StopIteration as error:
        raise ValueError("USBR station CSV header is missing") from error
    rows = csv.DictReader(io.StringIO("\n".join(lines[header_index:])))
    ids = {str(row.get("siteid", "")).strip().upper() for row in rows}
    ids.discard("")
    if not ids:
        raise ValueError("USBR station CSV contains no station IDs")
    return ids


def _normalize_feature(feature: dict[str, object]) -> dict[str, object]:
    properties = feature["properties"]
    geometry = feature["geometry"]
    assert isinstance(properties, dict)
    assert isinstance(geometry, dict)
    coordinates = geometry["coordinates"]
    assert isinstance(coordinates, list)
    station_id = str(properties["siteid"]).strip().upper()
    install_raw = str(properties.get("install", "")).strip()
    elevation_raw = str(properties.get("elevation", "")).strip()
    units = str(properties.get("elevationUnits", "")).strip().lower()
    elevation_m = _elevation_m(elevation_raw, units)
    return {
        "station_id": station_id,
        "description": str(properties.get("description", "")).strip(),
        "state": str(properties.get("state", "")).strip().upper(),
        "latitude": float(coordinates[1]),
        "longitude": float(coordinates[0]),
        "elevation_m": elevation_m,
        "installation_date": _installation_date(install_raw),
        "installation_date_raw": install_raw,
        "station_uri": STATION_PAGE + str(properties.get("url", "")),
        "responsibility": str(properties.get("responsibility", "")).strip(),
        "historical_location_status": "current_snapshot_only",
    }


def _elevation_m(value: str, units: str) -> Optional[float]:
    if not value:
        return None
    try:
        elevation = float(value)
    except ValueError:
        return None
    if units in {"m", "meter", "meters"}:
        return elevation
    if units in {"ft", "feet", "foot"}:
        return elevation * 0.3048
    return None


def _installation_date(value: str) -> Optional[str]:
    if not value:
        return None
    candidates = (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%d-%b-%Y",
    )
    for pattern in candidates:
        try:
            return datetime.strptime(value[:11], pattern).date().isoformat()
        except ValueError:
            continue
    return None


def _write_raw_sources(raw_root: Path, sources: dict[str, bytes]) -> None:
    if raw_root.exists() or raw_root.is_symlink():
        raise ValueError("raw-root must not already exist")
    if not raw_root.parent.is_dir() or raw_root.parent.is_symlink():
        raise ValueError("raw-root parent must be a real directory")
    raw_root.mkdir()
    for name, contents in sources.items():
        _write_new(raw_root / f"{name}.source", contents)


def _write_new(path: Path, contents: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(contents)
    path.chmod(0o444)


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
