#!/usr/bin/env python3
"""Decode one verified GEFSv12 raw issue into a canonical daily artifact."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from pathlib import Path

from mlet.sources.gefs import serialize_gefs_daily_artifact
from mlet.sources.gefs_reforecast_acquisition import (
    load_verified_gefs_reforecast_receipt,
)
from mlet.sources.gefs_reforecast_batch import decode_gefs_reforecast_issue

_NOAA_COLLECTION_URI = "https://registry.opendata.aws/noaa-gefs-reforecast/"


def _issue_time_arg(value: str) -> datetime:
    """Parse one strict UTC GEFS issue timestamp."""
    if not value.endswith("Z"):
        raise argparse.ArgumentTypeError("issue time must use strict UTC text ending in Z")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "issue time must use YYYY-MM-DDTHH:MM:SSZ"
        ) from error
    return parsed


def _bbox_arg(value: str) -> tuple[float, float, float, float]:
    """Parse a west,south,east,north bounding box."""
    try:
        values = tuple(float(item) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("bbox must use west,south,east,north") from error
    if len(values) != 4:
        raise argparse.ArgumentTypeError("bbox must use west,south,east,north")
    return values


def main() -> int:
    """Re-hash one raw receipt and write exactly one new daily artifact."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--issue-time", required=True, type=_issue_time_arg)
    parser.add_argument("--idaho-bbox", required=True, type=_bbox_arg)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--raw-receipt-uri", type=str)
    args = parser.parse_args()

    raw_objects = load_verified_gefs_reforecast_receipt(
        args.receipt,
        data_root=args.data_root,
    )
    receipt_path = args.receipt.resolve(strict=True)
    raw_receipt_uri = args.raw_receipt_uri or receipt_path.as_uri()
    decoded_rows = decode_gefs_reforecast_issue(
        raw_objects,
        issue_time=args.issue_time,
        idaho_bbox=args.idaho_bbox,
    )
    artifact_bytes = serialize_gefs_daily_artifact(
        decoded_rows,
        upstream_uri=_NOAA_COLLECTION_URI,
        source_issue_at=args.issue_time.isoformat().replace("+00:00", "Z"),
        idaho_bbox=args.idaho_bbox,
        raw_object_receipt={
            "uri": raw_receipt_uri,
            "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            "object_count": 187,
        },
    )
    if args.artifact.exists() or args.artifact.is_symlink():
        raise ValueError("GEFS daily artifact destination must not already exist")
    if not args.artifact.parent.is_dir() or args.artifact.parent.is_symlink():
        raise ValueError("GEFS daily artifact parent must be a real directory")
    with args.artifact.open("xb") as handle:
        handle.write(artifact_bytes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
