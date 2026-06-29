"""Command-line interface for MLET."""

from __future__ import annotations

import argparse
import sys

from mlet.validator import validate_csv

MAX_DISPLAYED_ERRORS = 20


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mlet")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser(
        "validate-csv", help="Validate an ET time-series CSV file."
    )
    validate.add_argument("path", help="Path to the ET time-series CSV.")
    args = parser.parse_args(argv)
    return _run_validate(args.path)


def _run_validate(path: str) -> int:
    try:
        result = validate_csv(path)
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    if result.is_valid:
        if result.report is not None:
            print(result.report.to_text())
        return 0

    shown = result.errors[:MAX_DISPLAYED_ERRORS]
    for error in shown:
        print(f"error: {error}", file=sys.stderr)
    remaining = len(result.errors) - len(shown)
    if remaining > 0:
        print(f"... and {remaining} more", file=sys.stderr)
    return 1
