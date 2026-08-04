#!/usr/bin/env python3
"""Build the static viewer for one verified ETo research candidate."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from mlet.outlook.eto_site import build_eto_site


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_eto_site")
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_eto_site(args.source_dir, args.out)
    except (OSError, ValueError) as error:
        print(f"error: cannot build ETo site: {error}", file=sys.stderr)
        return 2
    print(f"site: {result.destination}")
    print(f"run_id: {result.run_id}")
    print(f"candidate_sha256: {result.candidate_sha256}")
    print(f"source_manifest_sha256: {result.source_manifest_sha256}")
    print(f"site_manifest_sha256: {result.site_manifest_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
