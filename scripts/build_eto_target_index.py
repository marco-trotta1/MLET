#!/usr/bin/env python3
"""Build checksum-bound AgriMet ETo target artifacts for GEFS issue cases."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import cast

from mlet.outlook.dates import outlook_valid_date
from mlet.outlook.eto_archive import build_eto_target_artifact
from mlet.outlook.manifest import RunManifest
from mlet.outlook.spatial import validate_spatial_fold
from mlet.sources.agrimet import (
    AgriMetEtosObservation,
    AgriMetGridMatch,
    normalize_agrimet_etos_rows,
)


_CASE_PATTERN = re.compile(
    r"^issue-(?P<issue>\d{8})-station-(?P<station>[A-Z0-9]+)-"
    r"season-(?P<season>DJF|MAM|JJA|SON)-fold-(?P<fold>[0-4])$"
)
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
_TARGET_KIND = "mlet.agrimet.historical-target-build-receipt"


def build_target_index(
    *,
    gefs_index: Path,
    rows_path: Path,
    exclusions_path: Path,
    mapping_path: Path,
    output_root: Path,
    target_index: Path,
) -> Path:
    """Build one station-specific target artifact for every GEFS case."""
    gefs_payload, gefs_root = _load_index(gefs_index, "mlet.eto.gefs-index")
    rows_bytes = Path(rows_path).read_bytes()
    exclusion_bytes = Path(exclusions_path).read_bytes()
    mapping_bytes = Path(mapping_path).read_bytes()
    observations = normalize_agrimet_etos_rows(_read_json_array(rows_bytes, "AgriMet rows"))
    exclusions = _read_json_array(exclusion_bytes, "AgriMet exclusions")
    mappings = _load_mappings(mapping_bytes)
    observations_by_key = {
        (observation.station_id, observation.valid_date): observation
        for observation in observations
    }
    exclusions_by_key = {
        (item["station_id"], date.fromisoformat(item["valid_date"])): item["reason"]
        for item in exclusions
        if isinstance(item, dict)
        and isinstance(item.get("station_id"), str)
        and isinstance(item.get("valid_date"), str)
        and isinstance(item.get("reason"), str)
    }
    baselines = _prior_year_baselines(observations)
    root = _prepare_empty_directory(output_root)
    targets_root = root / "targets"
    targets_root.mkdir()
    raw_cases = gefs_payload["issues"]
    assert isinstance(raw_cases, list)
    target_descriptors: list[dict[str, str]] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("GEFS index issue must be an object")
        case_id = _require_text(raw_case.get("case_id"), "case_id")
        station_id, declared_season, declared_fold = _case_identity(case_id)
        issue_time = _parse_utc(raw_case.get("issue_time"), "issue_time")
        if issue_time.strftime("%Y%m%d") != _case_issue_text(case_id):
            raise ValueError("case_id issue date does not match issue_time")
        mapping = mappings.get(station_id)
        if mapping is None:
            raise ValueError(f"missing grid mapping for station {station_id}")
        validate_spatial_fold(mapping["grid_id"], declared_fold)
        forecast_directory = _resolve_directory(
            gefs_root, raw_case.get("forecast_directory"), "forecast_directory"
        )
        manifest = RunManifest.from_json(
            (forecast_directory / "manifest.json").read_text(encoding="utf-8")
        )
        if manifest.issued_at != issue_time:
            raise ValueError("forecast manifest issued_at must match issue_time")
        target_observations, target_exclusions = _case_targets(
            station_id=station_id,
            issue_time=issue_time,
            season=declared_season,
            observations_by_key=observations_by_key,
            exclusions_by_key=exclusions_by_key,
            baselines=baselines,
        )
        if not target_observations:
            raise ValueError(f"case {case_id} has no eligible target observations")
        target_path = targets_root / f"{case_id}.json"
        build_eto_target_artifact(
            case_id=case_id,
            run_id=manifest.run_id,
            issue_time=issue_time,
            observations=target_observations,
            matches={
                station_id: AgriMetGridMatch(
                    station_id=station_id,
                    grid_id=mapping["grid_id"],
                    distance_km=mapping["distance_km"],
                )
            },
            baseline_p50_mm={
                (observation.station_id, observation.valid_date): baselines[
                    (observation.station_id, observation.valid_date)
                ]
                for observation in target_observations
            },
            destination=target_path,
            exclusions=target_exclusions,
        )
        target_path.chmod(0o444)
        target_descriptors.append(
            {"case_id": case_id, "target_path": f"targets/{target_path.name}"}
        )

    index_payload = {
        "schema_version": 1,
        "kind": "mlet.eto.agrimet-index",
        "targets": sorted(target_descriptors, key=lambda item: item["case_id"]),
    }
    _write_new(target_index, _canonical_json_bytes(index_payload))
    receipt = {
        "schema_version": 1,
        "kind": _TARGET_KIND,
        "baseline": {
            "method": "station_day_of_year_mean_prior_to_issue_year",
            "evaluated_year_excluded": True,
            "future_years_excluded": True,
            "spatial_holdout": "forecast_case_holdout_only",
        },
        "case_count": len(target_descriptors),
        "rows_sha256": _sha256(rows_bytes),
        "exclusions_sha256": _sha256(exclusion_bytes),
        "mapping_sha256": _sha256(mapping_bytes),
        "target_index_sha256": _sha256(target_index.read_bytes()),
    }
    _write_new(root / "target-build-receipt.json", _canonical_json_bytes(receipt))
    return target_index


def _case_targets(
    *,
    station_id: str,
    issue_time: datetime,
    season: str,
    observations_by_key: Mapping[tuple[str, date], AgriMetEtosObservation],
    exclusions_by_key: Mapping[tuple[str, date], str],
    baselines: Mapping[tuple[str, date], float],
) -> tuple[tuple[AgriMetEtosObservation, ...], tuple[dict[str, object], ...]]:
    observations: list[AgriMetEtosObservation] = []
    exclusions: list[dict[str, object]] = []
    for lead_day in range(1, 21):
        valid_date = outlook_valid_date(issue_time, lead_day)
        target_id = f"agrimet:{station_id}"
        if _SEASONS[valid_date.month] != season:
            exclusions.append(
                {
                    "target_id": target_id,
                    "valid_date": valid_date,
                    "reason": "outside_held_out_season",
                }
            )
            continue
        observation = observations_by_key.get((station_id, valid_date))
        if observation is None:
            exclusions.append(
                {
                    "target_id": target_id,
                    "valid_date": valid_date,
                    "reason": exclusions_by_key.get(
                        (station_id, valid_date), "target_not_acquired"
                    ),
                }
            )
            continue
        if (station_id, valid_date) not in baselines:
            exclusions.append(
                {
                    "target_id": target_id,
                    "valid_date": valid_date,
                    "reason": "baseline_support_missing",
                }
            )
            continue
        observations.append(observation)
    return tuple(observations), tuple(exclusions)


def _prior_year_baselines(
    observations: tuple[AgriMetEtosObservation, ...],
) -> dict[tuple[str, date], float]:
    values: defaultdict[tuple[str, int], list[tuple[int, float]]] = defaultdict(list)
    for observation in observations:
        values[(observation.station_id, observation.valid_date.timetuple().tm_yday)].append(
            (observation.valid_date.year, observation.etos_mm)
        )
    baselines: dict[tuple[str, date], float] = {}
    for observation in observations:
        prior = [
            value
            for year, value in values[
                (observation.station_id, observation.valid_date.timetuple().tm_yday)
            ]
            if year < observation.valid_date.year
        ]
        if prior:
            baselines[(observation.station_id, observation.valid_date)] = sum(prior) / len(prior)
    return baselines


def _load_mappings(contents: bytes) -> dict[str, dict[str, object]]:
    payload = _read_json_object(contents, "AgriMet grid mapping")
    if set(payload) != {
        "forecast_artifact_sha256",
        "kind",
        "mappings",
        "maximum_distance_km",
        "schema_version",
    }:
        raise ValueError("AgriMet grid mapping fields must match the schema")
    raw_mappings = payload["mappings"]
    if not isinstance(raw_mappings, list) or not raw_mappings:
        raise ValueError("AgriMet grid mapping must contain mappings")
    result: dict[str, dict[str, object]] = {}
    for raw in raw_mappings:
        if not isinstance(raw, dict) or set(raw) != {
            "distance_km",
            "grid_id",
            "latitude",
            "longitude",
            "station_id",
        }:
            raise ValueError("AgriMet grid mapping row fields are invalid")
        station_id = _require_text(raw["station_id"], "mapping station_id")
        if station_id in result:
            raise ValueError("AgriMet grid mapping station IDs must be unique")
        result[station_id] = cast(dict[str, object], raw)
    return result


def _load_index(path: Path, expected_kind: str) -> tuple[dict[str, object], Path]:
    supplied = Path(path)
    if supplied.is_symlink():
        raise ValueError("source index must not be a symlink")
    resolved = supplied.resolve(strict=True)
    payload = _read_json_object(resolved.read_bytes(), "GEFS index")
    if payload.get("schema_version") != 1 or payload.get("kind") != expected_kind:
        raise ValueError(f"source index must use kind {expected_kind}")
    if not isinstance(payload.get("issues"), list) or not payload["issues"]:
        raise ValueError("GEFS index issues must be a non-empty list")
    return payload, resolved.parent


def _case_identity(case_id: str) -> tuple[str, str, int]:
    match = _CASE_PATTERN.fullmatch(case_id)
    if match is None:
        raise ValueError("case_id must use the frozen issue-station-season-fold format")
    return match["station"], match["season"], int(match["fold"])


def _case_issue_text(case_id: str) -> str:
    match = _CASE_PATTERN.fullmatch(case_id)
    if match is None:
        raise ValueError("case_id must use the frozen issue-station-season-fold format")
    return match["issue"]


def _resolve_directory(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError(f"{label} must be a relative path")
    path = (root / value).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} must remain below the index directory") from error
    if not path.is_dir() or path.is_symlink():
        raise ValueError(f"{label} must be a real directory")
    return path


def _prepare_empty_directory(path: Path) -> Path:
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise ValueError("output_root must be a real directory")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or any(path.iterdir()):
        raise ValueError("output_root must be empty")
    return path.resolve(strict=True)


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
        raise ValueError(f"output parent must be a real directory: {path.parent}")
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


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--gefs-index", required=True, type=Path)
    parser.add_argument("--rows", required=True, type=Path)
    parser.add_argument("--exclusions", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--target-index", required=True, type=Path)
    args = parser.parse_args()
    build_target_index(
        gefs_index=args.gefs_index,
        rows_path=args.rows,
        exclusions_path=args.exclusions,
        mapping_path=args.mapping,
        output_root=args.output_root,
        target_index=args.target_index,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
