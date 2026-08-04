#!/usr/bin/env python3
"""Create and optionally retrieve the frozen GEFSv12 reforecast raw plan."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

from mlet.sources.gefs_reforecast_acquisition import retrieve_gefs_reforecast_plan
from mlet.sources.gefs_reforecast_plan import (
    build_gefs_reforecast_acquisition_plan,
    write_gefs_reforecast_acquisition_plan,
)
from mlet.sources.gefs_schedule import weekly_wednesday_00z_issues


def _date_arg(value: str) -> date:
    """Parse one explicit ISO calendar date."""
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


def main() -> int:
    """Write the plan, then retrieve it only when all output paths are explicit."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", required=True, type=_date_arg)
    parser.add_argument("--last", required=True, type=_date_arg)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if not args.plan_only and (args.data_root is None or args.receipt is None):
        parser.error("--data-root and --receipt are required unless --plan-only is set")
    if args.plan_only and (args.data_root is not None or args.receipt is not None):
        parser.error("--plan-only does not accept --data-root or --receipt")

    issues = weekly_wednesday_00z_issues(args.first, args.last)
    plan = build_gefs_reforecast_acquisition_plan(issues)
    write_gefs_reforecast_acquisition_plan(plan, args.plan)
    if args.plan_only:
        return 0
    assert args.data_root is not None
    assert args.receipt is not None
    retrieve_gefs_reforecast_plan(
        plan,
        data_root=args.data_root,
        receipt_path=args.receipt,
        retrieved_at=datetime.now(timezone.utc),
        max_workers=args.workers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
