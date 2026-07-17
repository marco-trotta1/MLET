"""Command-line interface for MLET."""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

from mlet.build_dataset import build_dataset
from mlet.experiments import phase2_openet_value
from mlet.loader import load_site_series
from mlet.outlook.build import build_outlook
from mlet.outlook.hindcast import (
    evaluate_hindcast_evidence,
    write_hindcast_markdown,
    write_hindcast_validation,
    write_release_authority_request,
)
from mlet.outlook.publish import publish_outlook
from mlet.sources.gridmet import extract_eto
from mlet.sources.gefs import fetch_gefs
from mlet.sources.stations import load_station_metadata
from mlet.validator import validate_csv

MAX_DISPLAYED_ERRORS = 20


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mlet")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-csv", help="Validate an ET time-series CSV file.")
    validate.add_argument("path", help="Path to the ET time-series CSV.")
    build = subparsers.add_parser("build-dataset", help="Join public sources into contract CSVs.")
    build.add_argument("--openet", required=True)
    build.add_argument("--flux-dir", required=True)
    build.add_argument("--metadata", required=True)
    build.add_argument("--out", required=True)
    qc = subparsers.add_parser("qc-gridmet", help="Compare contract ETo with raw gridMET extraction.")
    qc.add_argument("--interim", required=True)
    qc.add_argument("--gridmet-dir", required=True)
    qc.add_argument("--metadata", required=True)
    qc.add_argument("--n", type=int, default=5)
    experiment = subparsers.add_parser("evaluate", help="Run the pre-registered Phase 2 experiment.")
    experiment.add_argument("--interim", required=True)
    experiment.add_argument("--landcover", required=True)
    experiment.add_argument("--out", required=True)
    fetch_outlook = subparsers.add_parser(
        "fetch-outlook-inputs",
        help="Acquire reproducible Idaho outlook inputs when source adapters are available.",
    )
    fetch_outlook.add_argument("--issue-date", required=True, metavar="YYYY-MM-DD")
    fetch_outlook.add_argument("--out", required=True)
    build_outlook_parser = subparsers.add_parser(
        "build-outlook", help="Build an immutable 20-day Idaho ET outlook artifact."
    )
    build_outlook_parser.add_argument("--weather", required=True)
    build_outlook_parser.add_argument("--state", required=True)
    build_outlook_parser.add_argument("--crop", required=True)
    build_outlook_parser.add_argument("--out", required=True)
    hindcast = subparsers.add_parser(
        "hindcast-outlook",
        help="Run the preregistered no-lookahead Idaho outlook release gate.",
    )
    hindcast.add_argument("--cases", required=True)
    hindcast.add_argument("--out", required=True)
    publish = subparsers.add_parser(
        "publish-outlook",
        help="Render a standalone, non-promotable Idaho outlook map candidate.",
    )
    publish.add_argument("--run", required=True, help="Published OUTPUT_ROOT/RUN_ID handle.")
    publish.add_argument(
        "--out",
        help="New candidate directory; defaults beside the immutable run handle.",
    )
    args = parser.parse_args(argv)
    if args.command == "validate-csv":
        return _run_validate(args.path)
    if args.command == "build-dataset":
        print(build_dataset(args.openet, args.flux_dir, args.metadata, args.out))
        return 0
    if args.command == "qc-gridmet":
        return _run_gridmet_qc(args.interim, args.gridmet_dir, args.metadata, args.n)
    if args.command == "fetch-outlook-inputs":
        return _run_fetch_outlook_inputs(args.issue_date, args.out)
    if args.command == "build-outlook":
        return _run_build_outlook(args.weather, args.state, args.crop, args.out)
    if args.command == "hindcast-outlook":
        return _run_hindcast_outlook(args.cases, args.out)
    if args.command == "publish-outlook":
        return _run_publish_outlook(args.run, args.out)
    result = phase2_openet_value.run(args.interim, args.landcover)
    _write_report(args.out, result)
    print(f"decision: {result['decision']}")
    return 0


def _run_fetch_outlook_inputs(issue_date_text: str, destination: str) -> int:
    """Return a source-failure code until live source adapters are reproducible."""
    try:
        issue_date = date.fromisoformat(issue_date_text)
        if issue_date.isoformat() != issue_date_text:
            raise ValueError("issue date must use YYYY-MM-DD")
        fetch_gefs(
            issue_date,
            (-118.0, 41.0, -110.0, 50.0),
            Path(destination),
        )
    except (NotImplementedError, OSError, ValueError) as exc:
        print(f"error: cannot fetch reproducible outlook inputs: {exc}", file=sys.stderr)
        return 2
    print("error: source acquisition did not produce a complete outlook input set", file=sys.stderr)
    return 2


def _run_build_outlook(weather: str, state: str, crop: str, destination: str) -> int:
    """Build only a complete, normalized outlook or return the data error code."""
    try:
        result = build_outlook(
            weather_path=Path(weather),
            state_path=Path(state),
            crop_path=Path(crop),
            out_dir=Path(destination),
        )
    except (OSError, ValueError) as exc:
        print(f"error: cannot build outlook: {exc}", file=sys.stderr)
        return 1
    print(f"run_id: {result.run_id}")
    print(f"out_root: {result.output_root}")
    print("read: use mlet.outlook.build.read_published_run(out_root, run_id)")
    return 0


def _run_hindcast_outlook(cases_path: str, destination: str) -> int:
    """Write the auditable hindcast report and return its release-gate status."""
    try:
        report_path = _trusted_hindcast_output(Path(destination))
        report, receipt = evaluate_hindcast_evidence(Path(cases_path))
        write_hindcast_validation(receipt, report_path.parent / "validation.json")
        write_release_authority_request(receipt, report_path.parent / "authority_request.json")
        write_hindcast_markdown(report, report_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot run outlook hindcast: {exc}", file=sys.stderr)
        return 2
    print(f"report: {report_path}")
    print(f"validation: {report_path.parent / 'validation.json'}")
    print(f"authority request: {report_path.parent / 'authority_request.json'}")
    print("promotion: false")
    return 1


def _run_publish_outlook(run: str, destination: str | None) -> int:
    """Render a research candidate and preserve the external-authority gate."""
    try:
        result = publish_outlook(
            Path(run), out_dir=Path(destination) if destination is not None else None
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot publish outlook candidate: {exc}", file=sys.stderr)
        return 2
    print(f"index: {result.index_path}")
    print(f"geojson: {result.geojson_path}")
    print(f"serve_contract: {result.serve_contract_path}")
    print(f"schema_version: {result.schema_version}")
    print(f"run_id: {result.run_id}")
    print("promotion: false")
    print("validation: pending")
    return 1


def _trusted_hindcast_output(destination: Path) -> Path:
    """Permit reports only under repository results or the local temporary root."""
    resolved = destination.resolve(strict=False)
    roots = (
        (Path.cwd() / "docs" / "results").resolve(strict=False),
        Path(tempfile.gettempdir()).resolve(strict=False),
        Path("/private/tmp").resolve(strict=False),
    )
    if any(_is_relative_to(resolved, root) for root in roots):
        return resolved
    raise ValueError(
        "hindcast output must be under docs/results or the local temporary directory"
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


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
    for error in result.errors[:MAX_DISPLAYED_ERRORS]:
        print(f"error: {error}", file=sys.stderr)
    remaining = len(result.errors) - MAX_DISPLAYED_ERRORS
    if remaining > 0:
        print(f"... and {remaining} more", file=sys.stderr)
    return 1


def _run_gridmet_qc(interim: str, gridmet_dir: str, metadata_path: str, count: int) -> int:
    metadata = load_station_metadata(metadata_path)
    rows: list[float] = []
    checked = 0
    for csv_path in sorted(Path(interim).glob("*.csv")):
        if csv_path.name == "all_stations.csv" or checked >= count:
            continue
        series = load_site_series(str(csv_path))
        station = metadata.get(series.site_id)
        if station is None:
            continue
        available = {record.date.isoformat(): record.eto_mm for record in series.records if record.eto_mm is not None}
        paths = sorted(str(path) for path in Path(gridmet_dir).glob("pet_*.nc"))
        extracted = extract_eto(paths, station.latitude, station.longitude, list(available))
        deltas = [abs(extracted[day] - eto) for day, eto in available.items() if day in extracted]
        if not deltas:
            continue
        checked += 1
        rows.extend(deltas)
        print(f"{series.site_id}: mean_abs_delta_mm={float(np.mean(deltas)):.3f} n={len(deltas)}")
    if not rows:
        print("error: no overlapping gridMET QC rows", file=sys.stderr)
        return 1
    print(f"overall: mean_abs_delta_mm={float(np.mean(rows)):.3f} n={len(rows)} stations={checked}")
    return 0


def _write_report(path: str, result: dict[str, object]) -> None:
    field = result["field_withheld"]
    assert isinstance(field, dict)
    models = field["models"]
    assert isinstance(models, dict)
    lines = ["# Phase 2 — OpenET-value results", "", f"Stations: {result['n_stations']}", "", "## Field-withheld", "", "| model | MAE (mm) | RMSE (mm) | bias (mm) | n |", "|---|---:|---:|---:|---:|"]
    for name, metric in models.items():
        assert isinstance(metric, dict)
        lines.append(f"| {name} | {float(metric['mae']):.3f} | {float(metric['rmse']):.3f} | {float(metric['bias']):.3f} | {int(metric['n'])} |")
    h2 = field["h2"]
    assert isinstance(h2, dict)
    lines.extend(["", "## H2 — OpenET value", "", f"Best OpenET-free model: {h2['best_free_model']}", f"MAE reduction: {float(h2['mae_reduction_frac']) * 100:.1f}%", f"MAE delta: {float(h2['delta_mm']):.3f} mm; 95% CI [{float(h2['ci95'][0]):.3f}, {float(h2['ci95'][1]):.3f}]", "", f"**OpenET-value decision:** {result['decision']}", "", "## Stratified H2", ""])
    strata = result["strata"]
    assert isinstance(strata, dict)
    for name, contrast in strata.items():
        if contrast is None:
            lines.append(f"- {name}: insufficient stations for a contrast.")
            continue
        assert isinstance(contrast, dict)
        lines.append(f"- {name}: {contrast['best_free_model']}; reduction {float(contrast['mae_reduction_frac']) * 100:.1f}%; CI [{float(contrast['ci95'][0]):.3f}, {float(contrast['ci95'][1]):.3f}].")
    lines.extend(["", "## Time-withheld", "", "This parallel split trains through 2018 and tests from 2019. It is descriptive and does not change the pre-registered primary decision.", ""])
    time = result["time_withheld"]
    assert isinstance(time, dict)
    time_models = time["models"]
    assert isinstance(time_models, dict)
    lines.extend(["| model | MAE (mm) | RMSE (mm) | bias (mm) | n |", "|---|---:|---:|---:|---:|"])
    for name, metric in time_models.items():
        assert isinstance(metric, dict)
        lines.append(f"| {name} | {float(metric['mae']):.3f} | {float(metric['rmse']):.3f} | {float(metric['bias']):.3f} | {int(metric['n'])} |")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
