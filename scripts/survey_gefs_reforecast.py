#!/usr/bin/env python3
"""Survey the public GEFSv12 objects for an explicit issue schedule."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import json
from pathlib import Path
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from mlet.sources.gefs_reforecast_plan import build_gefs_reforecast_acquisition_plan
from mlet.sources.gefs_schedule import weekly_wednesday_00z_issues


_TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _date_arg(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


def _probe(object_plan: dict[str, object]) -> dict[str, object]:
    request = Request(
        object_plan["uri"],
        method="HEAD",
        headers={"User-Agent": "mlet-gefs-reforecast-survey/1"},
    )
    try:
        with urlopen(request, timeout=60, context=_TLS_CONTEXT) as response:
            content_length = response.headers.get("Content-Length")
            return {
                **object_plan,
                "status": response.status,
                "content_length": int(content_length) if content_length else None,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "error": None,
            }
    except HTTPError as error:
        return {
            **object_plan,
            "status": error.code,
            "content_length": None,
            "etag": None,
            "last_modified": None,
            "error": None,
        }
    except URLError as error:
        return {
            **object_plan,
            "status": None,
            "content_length": None,
            "etag": None,
            "last_modified": None,
            "error": type(error.reason).__name__,
        }


def _write_new(path: Path, payload: dict[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("survey output must not already exist")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("survey output parent must be a real directory")
    contents = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    with path.open("xb") as handle:
        handle.write(contents)
    path.chmod(0o444)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", required=True, type=_date_arg)
    parser.add_argument("--last", required=True, type=_date_arg)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be from 1 through 16")

    issues = weekly_wednesday_00z_issues(args.first, args.last)
    plan = build_gefs_reforecast_acquisition_plan(issues)
    objects = plan["objects"]
    assert isinstance(objects, list)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        records = list(executor.map(_probe, objects))
    statuses = Counter(str(record["status"]) for record in records)
    available = [
        record
        for record in records
        if record["status"] == 200 and isinstance(record["content_length"], int)
    ]
    payload = {
        "schema_version": 1,
        "kind": "mlet.gefs.reforecast-availability-survey",
        "surveyed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "workers": args.workers,
        "planned_object_count": len(records),
        "available_object_count": len(available),
        "available_byte_count": sum(record["content_length"] for record in available),
        "status_counts": dict(sorted(statuses.items())),
        "records": records,
    }
    _write_new(args.output, payload)
    print(
        json.dumps(
            {
                "planned_object_count": payload["planned_object_count"],
                "available_object_count": payload["available_object_count"],
                "available_byte_count": payload["available_byte_count"],
                "status_counts": payload["status_counts"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
