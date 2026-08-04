#!/usr/bin/env python3
"""Build the GEFS case index used by the schema-v4 ETo archive assembler."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import cast

from mlet.outlook.dates import outlook_valid_date
from mlet.outlook.manifest import RunManifest
from mlet.sources.agrimet import AgriMetEtosObservation, normalize_agrimet_etos_rows


_SEASONS = {
    12: "DJF",
    1: "DJF",
    2: "DJF",
    3: "MAM",
    4: "MAM",
    5: "MAM",
    6: "JJA",
    7: "JJA",
    8: "JJA",
    9: "SON",
    10: "SON",
    11: "SON",
}


def build_gefs_case_index(
    *,
    stream_index: Path,
    candidate_root: Path,
    rows_path: Path,
    mapping_path: Path,
    destination: Path,
) -> Path:
    """Build one GEFS index entry for every eligible station-season case."""
    stream_bytes = Path(stream_index).read_bytes()
    stream = _read_json_object(stream_bytes, "GEFS stream index")
    if stream.get("schema_version") != 1 or stream.get("kind") != "mlet.gefs.reforecast-stream-index":
        raise ValueError("GEFS stream index has an unsupported schema")
    raw_summaries = stream.get("issues")
    if not isinstance(raw_summaries, list) or not raw_summaries:
        raise ValueError("GEFS stream index issues must be a non-empty list")
    rows_bytes = Path(rows_path).read_bytes()
    mapping_bytes = Path(mapping_path).read_bytes()
    observations = normalize_agrimet_etos_rows(
        _read_json_array(rows_bytes, "AgriMet rows")
    )
    observations_by_key = {
        (observation.station_id, observation.valid_date): observation
        for observation in observations
    }
    baselines = _prior_year_baselines(observations)
    mappings = _load_mappings(mapping_bytes)
    output = Path(destination)
    output_root = output.parent.resolve(strict=True)
    candidate_directory = Path(candidate_root).resolve(strict=True)
    try:
        candidate_relative = candidate_directory.relative_to(output_root)
    except ValueError as error:
        raise ValueError("candidate_root must remain below the GEFS index directory") from error
    issues = []
    issue_seen: set[str] = set()
    case_count = 0
    for summary in raw_summaries:
        if not isinstance(summary, dict):
            raise ValueError("GEFS stream issue summary must be an object")
        issue_time = _parse_utc(summary.get("issue_time"), "issue_time")
        issue_text = _format_utc(issue_time)
        if issue_text in issue_seen:
            raise ValueError("GEFS stream index must not duplicate issue times")
        issue_seen.add(issue_text)
        candidate_name = summary.get("candidate_path")
        if not isinstance(candidate_name, str) or not candidate_name:
            raise ValueError("GEFS stream summary must name a candidate directory")
        candidate = (candidate_directory / candidate_name).resolve(strict=True)
        try:
            candidate.relative_to(candidate_directory)
        except ValueError as error:
            raise ValueError("candidate_path escapes candidate_root") from error
        if not candidate.is_dir() or candidate.is_symlink():
            raise ValueError("candidate_path must name a real directory")
        manifest = RunManifest.from_json(
            (candidate / "manifest.json").read_text(encoding="utf-8")
        )
        if manifest.issued_at != issue_time:
            raise ValueError("candidate manifest issued_at must match stream issue_time")
        cases = []
        for station_id in sorted(mappings):
            mapping = mappings[station_id]
            fold = _fold_for_coordinates(mapping["latitude"], mapping["longitude"])
            for season in ("DJF", "MAM", "JJA", "SON"):
                if not _has_target_support(
                    station_id=station_id,
                    issue_time=issue_time,
                    season=season,
                    observations_by_key=observations_by_key,
                    baselines=baselines,
                ):
                    continue
                case_id = (
                    f"issue-{issue_time.strftime('%Y%m%d')}-station-{station_id}-"
                    f"season-{season}-fold-{fold}"
                )
                cases.append(
                    {
                        "case_id": case_id,
                        "issue_time": issue_text,
                        "forecast_directory": (candidate_relative / candidate_name).as_posix(),
                        "source_available_at": {"gefs": issue_text},
                        "held_out_fold": fold,
                        "held_out_season": season,
                    }
                )
        issues.extend(cases)
        case_count += len(cases)
    if not issues:
        raise ValueError("GEFS case index has no eligible station-season cases")
    payload = {
        "schema_version": 1,
        "kind": "mlet.eto.gefs-index",
        "issues": sorted(issues, key=lambda item: item["case_id"]),
    }
    _write_new(output, _canonical_json_bytes(payload))
    receipt = {
        "schema_version": 1,
        "kind": "mlet.eto.gefs-case-index-receipt",
        "issue_count": len(issue_seen),
        "case_count": case_count,
        "station_count": len(mappings),
        "stream_index_sha256": _sha256(stream_bytes),
        "rows_sha256": _sha256(rows_bytes),
        "mapping_sha256": _sha256(mapping_bytes),
        "gefs_index_sha256": _sha256(output.read_bytes()),
    }
    receipt_path = output.with_name(f"{output.stem}-receipt.json")
    _write_new(receipt_path, _canonical_json_bytes(receipt))
    return output


def _has_target_support(
    *,
    station_id: str,
    issue_time: datetime,
    season: str,
    observations_by_key: Mapping[tuple[str, date], AgriMetEtosObservation],
    baselines: Mapping[tuple[str, date], float],
) -> bool:
    for lead_day in range(1, 21):
        valid_date = outlook_valid_date(issue_time, lead_day)
        if _SEASONS[valid_date.month] != season:
            continue
        key = (station_id, valid_date)
        if key in observations_by_key and key in baselines:
            return True
    return False


def _prior_year_baselines(
    observations: tuple[AgriMetEtosObservation, ...],
) -> dict[tuple[str, date], float]:
    values: defaultdict[tuple[str, int], list[tuple[int, float]]] = defaultdict(list)
    for observation in observations:
        values[(observation.station_id, observation.valid_date.timetuple().tm_yday)].append(
            (observation.valid_date.year, observation.etos_mm)
        )
    result: dict[tuple[str, date], float] = {}
    for observation in observations:
        prior = [
            value
            for year, value in values[
                (observation.station_id, observation.valid_date.timetuple().tm_yday)
            ]
            if year < observation.valid_date.year
        ]
        if prior:
            result[(observation.station_id, observation.valid_date)] = sum(prior) / len(prior)
    return result


def _load_mappings(contents: bytes) -> dict[str, dict[str, float | str]]:
    payload = _read_json_object(contents, "AgriMet grid mapping")
    raw_mappings = payload.get("mappings")
    if not isinstance(raw_mappings, list) or not raw_mappings:
        raise ValueError("AgriMet grid mapping must contain mappings")
    result: dict[str, dict[str, float | str]] = {}
    for raw in raw_mappings:
        if not isinstance(raw, dict):
            raise ValueError("AgriMet mapping row must be an object")
        station_id = _require_text(raw.get("station_id"), "mapping station_id")
        if station_id in result:
            raise ValueError("AgriMet mapping station IDs must be unique")
        result[station_id] = {
            "grid_id": _require_text(raw.get("grid_id"), "mapping grid_id"),
            "latitude": _require_number(raw.get("latitude"), "mapping latitude"),
            "longitude": _require_number(raw.get("longitude"), "mapping longitude"),
            "distance_km": _require_number(raw.get("distance_km"), "mapping distance_km"),
        }
    return result


def _fold_for_coordinates(latitude: float | str, longitude: float | str) -> int:
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise ValueError("mapping coordinates must be numeric")
    block = f"{int(latitude // 1)}:{int(longitude // 1)}"
    digest = hashlib.sha256(f"idaho-outlook-v1:{block}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % 5


def _read_json_object(contents: bytes, label: str) -> dict[str, object]:
    value = json.loads(contents.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _read_json_array(contents: bytes, label: str) -> list[dict[str, object]]:
    value = json.loads(contents.decode("utf-8"))
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a JSON object array")
    return cast(list[dict[str, object]], value)


def _write_new(path: Path, contents: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"output already exists: {path}")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("output parent must be a real directory")
    with path.open("xb") as handle:
        handle.write(contents)
    path.chmod(0o444)


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _require_number(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be strict UTC text")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be strict UTC text") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be strict UTC text")
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--stream-index", required=True, type=Path)
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--rows", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--gefs-index", required=True, type=Path)
    args = parser.parse_args()
    build_gefs_case_index(
        stream_index=args.stream_index,
        candidate_root=args.candidate_root,
        rows_path=args.rows,
        mapping_path=args.mapping,
        destination=args.gefs_index,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
