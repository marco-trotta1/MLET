#!/usr/bin/env python3
"""Build deterministic manuscript artifacts from strict result records."""

from __future__ import annotations

import argparse
from pathlib import Path

from mlet.manuscript_artifacts import build_eto_hindcast_artifacts, build_phase2_artifacts


def main() -> int:
    """Parse explicit paths and generate new manuscript artifacts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase2", type=Path)
    parser.add_argument("--eto-hindcast", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.phase2 is None and args.eto_hindcast is None:
        parser.error("one of --phase2 or --eto-hindcast is required")
    if args.phase2 is not None:
        build_phase2_artifacts(args.phase2, args.out)
    if args.eto_hindcast is not None:
        build_eto_hindcast_artifacts(args.eto_hindcast, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
