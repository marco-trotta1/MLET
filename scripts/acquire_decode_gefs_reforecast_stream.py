#!/usr/bin/env python3
"""Acquire and decode a GEFS reforecast plan one issue at a time."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time

from mlet.outlook.eto_build import build_eto_outlook_from_gefs
from mlet.sources.gefs import serialize_gefs_daily_artifact
from mlet.sources.gefs import materialize_gefs_daily_artifact
from mlet.sources.gefs_reforecast_acquisition import (
    load_verified_gefs_reforecast_receipt,
    retrieve_gefs_reforecast_plan,
)
from mlet.sources.gefs_reforecast_batch import decode_gefs_reforecast_issue
from mlet.sources.gefs_reforecast_plan import build_gefs_reforecast_acquisition_plan


_COLLECTION_URI = "https://registry.opendata.aws/noaa-gefs-reforecast/"
_BYTES_PER_MB = 1_000_000.0


def issue_plans_from_full_plan(plan: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    """Split one canonical full plan into canonical one-issue plans."""
    if set(plan) != {"schema_version", "kind", "objects"}:
        raise ValueError("GEFS full plan fields must match the fixed schema")
    objects = plan["objects"]
    if not isinstance(objects, list) or not objects:
        raise ValueError("GEFS full plan must contain objects")
    issue_texts = sorted(
        {
            item["issue_time"]
            for item in objects
            if isinstance(item, dict) and isinstance(item.get("issue_time"), str)
        }
    )
    if not issue_texts or len(issue_texts) * 187 != len(objects):
        raise ValueError("GEFS full plan must contain 187 objects for every issue")
    try:
        issue_times = tuple(_parse_utc(value) for value in issue_texts)
    except (TypeError, ValueError) as error:
        raise ValueError("GEFS full plan issue times must be strict UTC timestamps") from error
    expected = build_gefs_reforecast_acquisition_plan(issue_times)
    if _canonical_json_bytes(plan) != _canonical_json_bytes(expected):
        raise ValueError("GEFS full plan does not match the frozen source layout")
    return tuple(build_gefs_reforecast_acquisition_plan((issue,)) for issue in issue_times)


def build_stream_index(
    *,
    plan_sha256: str,
    summaries: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Build a compact index over immutable per-issue summary receipts."""
    if len(plan_sha256) != 64 or any(character not in "0123456789abcdef" for character in plan_sha256):
        raise ValueError("plan_sha256 must be lowercase SHA-256 hexadecimal")
    ordered = sorted(summaries, key=lambda value: str(value["issue_time"]))
    issue_times = [value.get("issue_time") for value in ordered]
    if any(not isinstance(value, str) for value in issue_times):
        raise ValueError("stream summaries must contain issue_time text")
    if len(set(issue_times)) != len(issue_times):
        raise ValueError("stream summaries must not duplicate issue times")
    return {
        "schema_version": 1,
        "kind": "mlet.gefs.reforecast-stream-index",
        "plan_sha256": plan_sha256,
        "issue_count": len(ordered),
        "issues": [dict(value) for value in ordered],
    }


def main() -> int:
    """Acquire selected issues and write a new compact completion index."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--receipts-root", required=True, type=Path)
    parser.add_argument("--artifacts-root", required=True, type=Path)
    parser.add_argument("--candidates-root", type=Path)
    parser.add_argument("--git-revision")
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--idaho-bbox", required=True, type=_bbox_arg)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--keep-raw", action="store_true")
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 16:
        parser.error("--workers must be from 1 through 16")
    if args.timeout_seconds < 1.0 or args.timeout_seconds > 3_600.0:
        parser.error("--timeout-seconds must be from 1 through 3600")
    if (args.candidates_root is None) != (args.git_revision is None):
        parser.error("--candidates-root and --git-revision must be supplied together")
    if args.start_index < 0:
        parser.error("--start-index must not be negative")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.index.exists() or args.index.is_symlink():
        parser.error("--index destination must not already exist")

    plan_bytes = args.plan.read_bytes()
    plan = _read_json_object(plan_bytes, "GEFS full plan")
    issue_plans = issue_plans_from_full_plan(plan)
    end_index = len(issue_plans) if args.limit is None else args.start_index + args.limit
    if args.start_index >= len(issue_plans):
        parser.error("--start-index is outside the full plan")
    selected = issue_plans[args.start_index : min(end_index, len(issue_plans))]

    raw_root = _prepare_directory(args.raw_root)
    receipts_root = _prepare_directory(args.receipts_root)
    artifacts_root = _prepare_directory(args.artifacts_root)
    candidates_root = (
        _prepare_directory(args.candidates_root)
        if args.candidates_root is not None
        else None
    )
    summaries: list[Mapping[str, object]] = []
    for issue_plan in selected:
        issue_time = _issue_from_plan(issue_plan)
        timestamp = issue_time.strftime("%Y%m%d%H")
        summary_path = receipts_root / f"{timestamp}.issue.json"
        raw_receipt_path = receipts_root / f"{timestamp}.raw.json"
        artifact_path = artifacts_root / f"{timestamp}.daily-artifact.json"
        candidate_path = (
            candidates_root / timestamp if candidates_root is not None else None
        )
        if args.resume and summary_path.is_file() and artifact_path.is_file():
            summary = _read_json_object(summary_path.read_bytes(), "GEFS issue summary")
            _verify_summary_artifact(summary, artifact_path, candidate_path)
            summaries.append(summary)
            continue
        if any(
            path.exists() or path.is_symlink()
            for path in (summary_path, raw_receipt_path, artifact_path)
        ):
            raise ValueError(f"GEFS issue {timestamp} has partial or existing outputs; use a new root")
        if candidate_path is not None and (candidate_path.exists() or candidate_path.is_symlink()):
            raise ValueError(f"GEFS issue candidate directory already exists: {candidate_path}")
        issue_raw = raw_root / timestamp
        if issue_raw.exists() or issue_raw.is_symlink():
            raise ValueError(f"GEFS issue raw directory already exists: {issue_raw}")
        issue_raw.mkdir()
        summary = _acquire_one_issue(
            issue_plan,
            issue_raw=issue_raw,
            raw_receipt_path=raw_receipt_path,
            artifact_path=artifact_path,
            summary_path=summary_path,
            idaho_bbox=args.idaho_bbox,
            workers=args.workers,
            timeout_seconds=args.timeout_seconds,
            candidate_path=candidate_path,
            git_revision=args.git_revision,
            keep_raw=args.keep_raw,
        )
        summaries.append(summary)

    index = build_stream_index(
        plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
        summaries=summaries,
    )
    _write_new(args.index, _canonical_json_bytes(index))
    return 0


def _acquire_one_issue(
    issue_plan: Mapping[str, object],
    *,
    issue_raw: Path,
    raw_receipt_path: Path,
    artifact_path: Path,
    summary_path: Path,
    idaho_bbox: tuple[float, float, float, float],
    workers: int,
    timeout_seconds: float,
    candidate_path: Path | None,
    git_revision: str | None,
    keep_raw: bool,
) -> dict[str, object]:
    issue_time = _issue_from_plan(issue_plan)
    transfer_started = datetime.now(timezone.utc)
    transfer_clock = time.monotonic()
    before_free = shutil.disk_usage(issue_raw).free
    retrieve_gefs_reforecast_plan(
        issue_plan,
        data_root=issue_raw,
        receipt_path=raw_receipt_path,
        retrieved_at=transfer_started,
        max_workers=workers,
        timeout_seconds=timeout_seconds,
    )
    transfer_elapsed = time.monotonic() - transfer_clock
    raw_objects = load_verified_gefs_reforecast_receipt(
        raw_receipt_path,
        data_root=issue_raw,
    )
    raw_byte_count = sum(path.stat().st_size for path in issue_raw.rglob("*" ) if path.is_file())
    workspace_bytes = _directory_size(issue_raw)
    after_download_free = shutil.disk_usage(issue_raw).free

    decode_started = time.monotonic()
    rows = decode_gefs_reforecast_issue(
        raw_objects,
        issue_time=issue_time,
        idaho_bbox=idaho_bbox,
    )
    artifact_bytes = serialize_gefs_daily_artifact(
        rows,
        upstream_uri=_COLLECTION_URI,
        source_issue_at=_format_utc(issue_time),
        idaho_bbox=idaho_bbox,
        raw_object_receipt={
            "uri": raw_receipt_path.resolve().as_uri(),
            "sha256": _sha256_file(raw_receipt_path),
            "object_count": len(raw_objects),
        },
    )
    _write_new(artifact_path, artifact_bytes)
    decode_elapsed = time.monotonic() - decode_started
    candidate_manifest = None
    candidate_outlook = None
    candidate_run_id = None
    if candidate_path is not None and git_revision is not None:
        candidate_path.mkdir()
        pointer_path = artifact_path.with_suffix(".gefs")
        artifact_set = materialize_gefs_daily_artifact(artifact_path, pointer_path)
        manifest = build_eto_outlook_from_gefs(
            artifact_set=artifact_set,
            git_revision=git_revision,
            retrieved_at=_format_utc(transfer_started),
            destination=candidate_path,
        )
        candidate_run_id = manifest.run_id
        candidate_manifest = _sha256_file(candidate_path / "manifest.json")
        candidate_outlook = _sha256_file(candidate_path / "outlook.json")
    raw_payload = _read_json_object(raw_receipt_path.read_bytes(), "GEFS raw receipt")
    response_metadata = _response_metadata(raw_payload)
    if not keep_raw:
        shutil.rmtree(issue_raw)
    finished_at = datetime.now(timezone.utc)
    summary = {
        "schema_version": 1,
        "kind": "mlet.gefs.reforecast-issue-stream-receipt",
        "issue_time": _format_utc(issue_time),
        "planned_object_count": len(issue_plan["objects"]),
        "retrieved_object_count": len(raw_objects),
        "raw_byte_count": raw_byte_count,
        "transfer_started_at": _format_utc(transfer_started),
        "transfer_finished_at": _format_utc(transfer_started + _seconds(transfer_elapsed)),
        "transfer_elapsed_seconds": round(transfer_elapsed, 6),
        "transfer_throughput_mb_per_second": round(
            raw_byte_count / transfer_elapsed / _BYTES_PER_MB, 6
        ),
        "filesystem_free_bytes_before": before_free,
        "filesystem_free_bytes_after_download": after_download_free,
        "raw_workspace_bytes_after_download": workspace_bytes,
        "response_metadata": response_metadata,
        "decoder_elapsed_seconds": round(decode_elapsed, 6),
        "decoded_row_count": len(rows),
        "raw_receipt_path": raw_receipt_path.name,
        "raw_receipt_sha256": _sha256_file(raw_receipt_path),
        "artifact_path": artifact_path.name,
        "artifact_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        "candidate_path": candidate_path.name if candidate_path is not None else None,
        "candidate_run_id": candidate_run_id,
        "candidate_manifest_sha256": candidate_manifest,
        "candidate_outlook_sha256": candidate_outlook,
        "raw_retained": keep_raw,
    }
    _write_new(summary_path, _canonical_json_bytes(summary))
    return summary


def _response_metadata(payload: Mapping[str, object]) -> dict[str, int]:
    objects = payload.get("objects")
    if not isinstance(objects, list):
        raise ValueError("GEFS raw receipt objects must be a list")
    return {
        "objects_with_etag": sum(
            isinstance(item, dict) and isinstance(item.get("etag"), str)
            for item in objects
        ),
        "objects_with_last_modified": sum(
            isinstance(item, dict) and isinstance(item.get("last_modified"), str)
            for item in objects
        ),
    }


def _verify_summary_artifact(
    summary: Mapping[str, object], artifact_path: Path, candidate_path: Path | None
) -> None:
    expected = summary.get("artifact_sha256")
    if not isinstance(expected, str) or _sha256_file(artifact_path) != expected:
        raise ValueError("existing GEFS issue artifact does not match its summary receipt")
    expected_manifest = summary.get("candidate_manifest_sha256")
    expected_outlook = summary.get("candidate_outlook_sha256")
    if expected_manifest is None and expected_outlook is None:
        return
    if candidate_path is None or not candidate_path.is_dir() or candidate_path.is_symlink():
        raise ValueError("existing GEFS issue candidate directory is missing")
    if not isinstance(expected_manifest, str) or not isinstance(expected_outlook, str):
        raise ValueError("existing GEFS issue candidate hashes are incomplete")
    if _sha256_file(candidate_path / "manifest.json") != expected_manifest:
        raise ValueError("existing GEFS issue candidate manifest does not match its receipt")
    if _sha256_file(candidate_path / "outlook.json") != expected_outlook:
        raise ValueError("existing GEFS issue candidate artifact does not match its receipt")


def _issue_from_plan(plan: Mapping[str, object]) -> datetime:
    objects = plan.get("objects")
    if not isinstance(objects, list) or not objects or not isinstance(objects[0], dict):
        raise ValueError("one-issue GEFS plan has no objects")
    issue_time = objects[0].get("issue_time")
    if not isinstance(issue_time, str):
        raise ValueError("one-issue GEFS plan has no issue time")
    return _parse_utc(issue_time)


def _bbox_arg(value: str) -> tuple[float, float, float, float]:
    try:
        values = tuple(float(item) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("bbox must use west,south,east,north") from error
    if len(values) != 4:
        raise argparse.ArgumentTypeError("bbox must use west,south,east,north")
    return values


def _parse_utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("UTC timestamp must end in Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamp must be explicit UTC")
    return parsed.astimezone(timezone.utc)


def _prepare_directory(path: Path) -> Path:
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        raise ValueError(f"directory must be a real directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"directory must not be a symlink: {path}")
    return path.resolve(strict=True)


def _read_json_object(contents: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _directory_size(path: Path) -> int:
    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


def _seconds(value: float) -> timedelta:
    return timedelta(seconds=value)


def _write_new(path: Path, contents: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"output already exists: {path}")
    with path.open("xb") as handle:
        handle.write(contents)
    path.chmod(0o444)


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
