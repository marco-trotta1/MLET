"""Build a self-contained ETo hindcast archive from source indexes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from mlet.outlook.eto_archive import (
    SourceTiming,
    assemble_eto_hindcast_evidence,
    combine_eto_hindcast_evidence,
)
from mlet.outlook.eto_hindcast import evaluate_eto_hindcast_evidence
from mlet.outlook.manifest import RunManifest


_GEFS_INDEX_KIND = "mlet.eto.gefs-index"
_AGRIMET_INDEX_KIND = "mlet.eto.agrimet-index"
_GEFS_INDEX_SCHEMA_VERSION = 2
_AGRIMET_INDEX_SCHEMA_VERSION = 1


def build_eto_hindcast_archive(
    gefs_index: Path,
    agrimet_index: Path,
    destination: Path,
) -> Path:
    """Build a schema-v4 archive from verified forecast and target indexes.

    The GEFS index points to immutable forecast directories. The AgriMet index
    points to immutable schema-v2 target artifacts. This function creates one
    issue evidence directory for every matched case, then bundles the cases
    below the destination. It does not download raw data.
    """
    gefs_cases = _load_gefs_index(Path(gefs_index))
    agrimet_cases = _load_agrimet_index(Path(agrimet_index))
    if set(gefs_cases) != set(agrimet_cases):
        raise ValueError("GEFS and AgriMet indexes must contain the same case IDs")
    archive_root = Path(destination)
    if not archive_root.is_dir() or archive_root.is_symlink() or any(archive_root.iterdir()):
        raise ValueError("archive destination must be an existing empty real directory")
    with tempfile.TemporaryDirectory(
        prefix="mlet-eto-cases-", dir=str(archive_root.parent)
    ) as staging_name:
        staging_root = Path(staging_name)
        evidence_paths: list[Path] = []
        for case_id in sorted(gefs_cases):
            forecast = gefs_cases[case_id]
            target = agrimet_cases[case_id]
            case_root = staging_root / case_id
            case_root.mkdir()
            manifest = RunManifest.from_json(
                (forecast.forecast_directory / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            evidence_paths.append(
                assemble_eto_hindcast_evidence(
                    case_id=case_id,
                    issue_time=forecast.issue_time,
                    forecast_directory=forecast.forecast_directory,
                    target_path=target.target_path,
                    source_timing={
                        source.name: forecast.timing for source in manifest.sources
                    },
                    held_out_fold=forecast.held_out_fold,
                    held_out_season=forecast.held_out_season,
                    destination=case_root,
                )
            )
        archive_path = combine_eto_hindcast_evidence(evidence_paths, archive_root)
    report = evaluate_eto_hindcast_evidence(archive_path)
    if report.case_count != len(gefs_cases):
        raise ValueError("ETo archive case count does not match the source indexes")
    _write_index_receipt(gefs_index, agrimet_index, archive_root)
    return archive_path


def bundle_eto_hindcast_evidence(
    evidence_paths: Sequence[Path], destination: Path
) -> Path:
    """Bundle already assembled issue evidence below one archive root.

    This compatibility helper supports review and fixture workflows. New
    archive builds should use :func:`build_eto_hindcast_archive`.
    """
    if not isinstance(evidence_paths, Sequence) or isinstance(evidence_paths, (str, bytes)):
        raise ValueError("ETo evidence_paths must be a sequence of paths")
    archive_path = combine_eto_hindcast_evidence(evidence_paths, destination)
    evaluate_eto_hindcast_evidence(archive_path)
    return archive_path


@dataclass(frozen=True)
class _GefsCase:
    issue_time: datetime
    forecast_directory: Path
    timing: SourceTiming
    held_out_fold: int
    held_out_season: str


@dataclass(frozen=True)
class _AgriMetCase:
    target_path: Path


def _load_gefs_index(path: Path) -> dict[str, _GefsCase]:
    payload, root = _load_index(path, _GEFS_INDEX_KIND, _GEFS_INDEX_SCHEMA_VERSION)
    _require_exact_keys(payload, {"schema_version", "kind", "issues"}, "GEFS index")
    raw_issues = payload["issues"]
    if not isinstance(raw_issues, list) or not raw_issues:
        raise ValueError("GEFS index issues must be a non-empty list")
    cases: dict[str, _GefsCase] = {}
    for raw in raw_issues:
        _require_exact_keys(
            raw,
            {
                "case_id",
                "issue_time",
                "forecast_directory",
                "temporal_role",
                "source_issue_at",
                "archive_available_at",
                "held_out_fold",
                "held_out_season",
            },
            "GEFS index issue",
        )
        assert isinstance(raw, dict)
        case_id = _case_id(raw["case_id"])
        if case_id in cases:
            raise ValueError("GEFS index case IDs must be unique")
        issue_time = _parse_utc(raw["issue_time"], "GEFS issue_time")
        timing = SourceTiming(
            temporal_role=_require_text(raw["temporal_role"], "GEFS temporal_role"),
            source_issue_at=_parse_utc(raw["source_issue_at"], "GEFS source_issue_at"),
            archive_available_at=_parse_utc(
                raw["archive_available_at"], "GEFS archive_available_at"
            ),
        )
        if timing.source_issue_at != issue_time:
            raise ValueError("GEFS source_issue_at must match issue_time")
        forecast_directory = _resolve_directory(
            root, raw["forecast_directory"], "GEFS forecast_directory"
        )
        held_out_fold = raw["held_out_fold"]
        if type(held_out_fold) is not int or held_out_fold not in range(5):
            raise ValueError("GEFS held_out_fold must be an integer from 0 through 4")
        held_out_season = raw["held_out_season"]
        if held_out_season not in {"DJF", "MAM", "JJA", "SON"}:
            raise ValueError("GEFS held_out_season is invalid")
        cases[case_id] = _GefsCase(
            issue_time,
            forecast_directory,
            timing,
            held_out_fold,
            held_out_season,
        )
    return cases


def _load_agrimet_index(path: Path) -> dict[str, _AgriMetCase]:
    payload, root = _load_index(path, _AGRIMET_INDEX_KIND, _AGRIMET_INDEX_SCHEMA_VERSION)
    _require_exact_keys(payload, {"schema_version", "kind", "targets"}, "AgriMet index")
    raw_targets = payload["targets"]
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("AgriMet index targets must be a non-empty list")
    cases: dict[str, _AgriMetCase] = {}
    for raw in raw_targets:
        _require_exact_keys(raw, {"case_id", "target_path"}, "AgriMet index target")
        assert isinstance(raw, dict)
        case_id = _case_id(raw["case_id"])
        if case_id in cases:
            raise ValueError("AgriMet index case IDs must be unique")
        cases[case_id] = _AgriMetCase(
            _resolve_file(root, raw["target_path"], "AgriMet target_path")
        )
    return cases


def _load_index(
    path: Path, expected_kind: str, expected_schema_version: int
) -> tuple[dict[str, object], Path]:
    supplied = Path(path)
    if supplied.is_symlink():
        raise ValueError("source index must not be a symlink")
    resolved = supplied.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("source index must name a regular file")
    try:
        payload = json.loads(
            resolved.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("source index must be duplicate-key-free UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("source index must be a JSON object")
    if (
        payload.get("schema_version") != expected_schema_version
        or payload.get("kind") != expected_kind
    ):
        raise ValueError(
            f"source index must use schema_version {expected_schema_version} and kind {expected_kind}"
        )
    return payload, resolved.parent


def _resolve_directory(root: Path, value: object, label: str) -> Path:
    path = _resolve_path(root, value, label)
    if not path.is_dir():
        raise ValueError(f"{label} must name a directory")
    return path


def _resolve_file(root: Path, value: object, label: str) -> Path:
    path = _resolve_path(root, value, label)
    if not path.is_file():
        raise ValueError(f"{label} must name a regular file")
    return path


def _resolve_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError(f"{label} must be a non-empty relative path")
    supplied = root / value
    if supplied.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    path = supplied.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} must remain below its index directory") from error
    return path


def _write_index_receipt(gefs_index: Path, agrimet_index: Path, root: Path) -> None:
    copied_indexes = (
        (Path(gefs_index), root / "gefs-index.json"),
        (Path(agrimet_index), root / "agrimet-index.json"),
    )
    for source, destination in copied_indexes:
        with destination.open("xb") as handle:
            handle.write(source.read_bytes())
    payload = {
        "schema_version": 1,
        "kind": "mlet.eto.archive-index-receipt",
        "gefs_index": {
            "path": "gefs-index.json",
            "sha256": _sha256(Path(gefs_index).read_bytes()),
        },
        "agrimet_index": {
            "path": "agrimet-index.json",
            "sha256": _sha256(Path(agrimet_index).read_bytes()),
        },
    }
    destination = root / "archive-index-receipt.json"
    with destination.open("xb") as handle:
        handle.write(_canonical_json_bytes(payload))


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text")
    return parsed.astimezone(timezone.utc)


def _case_id(value: object) -> str:
    case_id = _require_text(value, "case_id")
    if not case_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("case_id must contain only letters, digits, hyphens, or underscores")
    return case_id


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _require_exact_keys(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields must match the schema exactly")


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()
