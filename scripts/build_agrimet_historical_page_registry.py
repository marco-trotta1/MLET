#!/usr/bin/env python3
"""Build a historical AgriMet registry from archived station pages and maps."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Optional


_MAP_SOURCE_URI = (
    "https://web.archive.org/web/20181228221543id_/"
    "https://www.usbr.gov/pn/agrimet/agrimetmap/usbr_map.json"
)
_MAP_SOURCE_SHA256 = "016b565d70e5280158b6ca9bf161bd83d13850f9d4ba7e4d47d3565a6b074cf6"
_UTC_PATTERN = "%Y-%m-%dT%H:%M:%SZ"
_COORDINATE_PATTERN = re.compile(
    r"(?P<label>Latitude|Longitude):\s*(?P<value>-?[0-9]+(?:\.[0-9]+)?)\s*(?P<hemisphere>[NSEW])",
    re.IGNORECASE,
)
_ELEVATION_PATTERN = re.compile(
    r"Elevation:\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*'",
    re.IGNORECASE,
)


def build_registry(
    *,
    page_root: Path,
    map_root: Path,
    cdx_root: Path,
    retrieved_at: str,
    valid_to: date,
) -> dict[str, object]:
    """Build one schema-v1 registry from checksum-bound archived inputs."""
    maps = _load_maps(map_root)
    stations = []
    for page_path in sorted(Path(page_root).glob("*.html")):
        station_id, page_stamp = _page_identity(page_path)
        page_text = html.unescape(page_path.read_text(encoding="utf-8"))
        latitude, longitude = _parse_coordinates(page_text)
        elevation_m = _parse_elevation_m(page_text)
        map_observations = _map_observations(maps, station_id)
        if not map_observations:
            raise ValueError(f"archived maps do not contain {station_id}")
        _require_matching_coordinates(station_id, latitude, longitude, map_observations)
        map_dates = [item["captured_at"] for item in map_observations]
        first_map_date = min(map_dates)
        last_map_date = max(map_dates)
        if last_map_date <= valid_to:
            raise ValueError(f"archived maps do not bracket the target window for {station_id}")
        metadata_uri = _metadata_uri(cdx_root / f"{station_id}.json", page_stamp)
        stations.append(
            {
                "station_id": station_id,
                "segments": [
                    {
                        "valid_from": first_map_date.isoformat(),
                        "valid_to": valid_to.isoformat(),
                        "latitude": latitude,
                        "longitude": longitude,
                        "elevation_m": elevation_m,
                        "metadata_uri": metadata_uri,
                        "metadata_sha256": _sha256_file(page_path),
                        "source_version": (
                            f"wayback-station-page-{page_stamp};"
                            f" wayback-map-snapshots-{','.join(item['captured_at'].isoformat() for item in map_observations)}"
                        ),
                    }
                ],
            }
        )
    if not stations:
        raise ValueError("no archived station pages were found")
    return {
        "schema_version": 1,
        "kind": "mlet.agrimet.station-history-registry",
        "source_snapshot": {
            "uri": _MAP_SOURCE_URI,
            "sha256": _MAP_SOURCE_SHA256,
            "retrieved_at": retrieved_at,
        },
        "stations": stations,
    }


def main() -> int:
    """Write one new historical registry from external archived inputs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--page-root", required=True, type=Path)
    parser.add_argument("--map-root", required=True, type=Path)
    parser.add_argument("--cdx-root", required=True, type=Path)
    parser.add_argument("--retrieved-at", required=True, type=_utc_arg)
    parser.add_argument("--valid-to", required=True, type=_date_arg)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = build_registry(
        page_root=args.page_root,
        map_root=args.map_root,
        cdx_root=args.cdx_root,
        retrieved_at=args.retrieved_at,
        valid_to=args.valid_to,
    )
    _write_new(args.output, _canonical_json_bytes(payload))
    print(json.dumps({"station_count": len(payload["stations"]), "output": str(args.output)}))
    return 0


def _load_maps(map_root: Path) -> tuple[tuple[date, dict[str, object], str], ...]:
    result = []
    for path in sorted(Path(map_root).glob("agrimet_map_*.json")):
        if path.name.endswith("_cdx.json"):
            continue
        match = re.search(r"(\d{8})", path.name)
        if match is None:
            raise ValueError(f"map filename has no capture date: {path.name}")
        captured_at = datetime.strptime(match.group(1), "%Y%m%d").date()
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("features"), list):
            raise ValueError(f"map snapshot is not a feature collection: {path}")
        result.append((captured_at, value, _sha256_file(path)))
    if not result:
        raise ValueError("no archived map snapshots were found")
    return tuple(result)


def _map_observations(
    maps: tuple[tuple[date, dict[str, object], str], ...], station_id: str
) -> list[dict[str, object]]:
    observations = []
    for captured_at, payload, map_sha256 in maps:
        matches = []
        for feature in payload["features"]:
            if not isinstance(feature, dict):
                continue
            properties = feature.get("properties")
            if not isinstance(properties, dict) or properties.get("state") != "ID":
                continue
            candidate = properties.get("siteid") or properties.get("cbtt") or feature.get("id")
            if isinstance(candidate, str) and candidate.upper() == station_id:
                geometry = feature.get("geometry")
                coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
                if not isinstance(coordinates, list) or len(coordinates) != 2:
                    raise ValueError(f"map feature has invalid coordinates for {station_id}")
                matches.append((float(coordinates[1]), float(coordinates[0])))
        if len(matches) != 1:
            continue
        observations.append(
            {
                "captured_at": captured_at,
                "latitude": matches[0][0],
                "longitude": matches[0][1],
                "map_sha256": map_sha256,
            }
        )
    return observations


def _require_matching_coordinates(
    station_id: str,
    latitude: float,
    longitude: float,
    observations: list[dict[str, object]],
) -> None:
    tolerance = 1e-6
    for observation in observations:
        if abs(latitude - float(observation["latitude"])) > tolerance:
            raise ValueError(f"latitude differs between page and map for {station_id}")
        if abs(longitude - float(observation["longitude"])) > tolerance:
            raise ValueError(f"longitude differs between page and map for {station_id}")
    coordinates = {
        (round(float(item["latitude"]), 6), round(float(item["longitude"]), 6))
        for item in observations
    }
    if len(coordinates) != 1:
        raise ValueError(f"map coordinates change across snapshots for {station_id}")


def _parse_coordinates(page_text: str) -> tuple[float, float]:
    values: dict[str, float] = {}
    for match in _COORDINATE_PATTERN.finditer(page_text):
        label = match.group("label").lower()
        value = float(match.group("value"))
        hemisphere = match.group("hemisphere").upper()
        if hemisphere in {"S", "W"}:
            value = -abs(value)
        values[label] = value
    if set(values) != {"latitude", "longitude"}:
        raise ValueError("archived station page must contain latitude and longitude")
    return values["latitude"], values["longitude"]


def _parse_elevation_m(page_text: str) -> float:
    match = _ELEVATION_PATTERN.search(page_text)
    if match is None:
        raise ValueError("archived station page must contain elevation in feet")
    return round(float(match.group("value")) * 0.3048, 6)


def _page_identity(path: Path) -> tuple[str, str]:
    match = re.fullmatch(r"([A-Z0-9]+)_(\d{14})", path.stem)
    if match is None:
        raise ValueError(f"station page filename must use STATION_TIMESTAMP: {path.name}")
    return match.group(1), match.group(2)


def _metadata_uri(path: Path, page_stamp: str) -> str:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"station CDX response is invalid: {path}")
    for row in value[1:]:
        if isinstance(row, list) and len(row) >= 2 and row[0] == page_stamp:
            return f"https://web.archive.org/web/{page_stamp}id_/{row[1]}"
    raise ValueError(f"station CDX response lacks page capture {page_stamp}: {path}")


def _date_arg(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD")
    return parsed


def _utc_arg(value: str) -> str:
    try:
        parsed = datetime.strptime(value, _UTC_PATTERN).replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise argparse.ArgumentTypeError("time must use YYYY-MM-DDTHH:MM:SSZ") from error
    return parsed.strftime(_UTC_PATTERN)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _write_new(path: Path, contents: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("registry output must not already exist")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("registry output parent must be a real directory")
    with path.open("xb") as handle:
        handle.write(contents)
    path.chmod(0o444)


if __name__ == "__main__":
    raise SystemExit(main())
