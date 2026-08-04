"""Command-line interface for MLET."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

from mlet.build_dataset import build_dataset
from mlet.experiments import phase2_openet_value
from mlet.experiments.idaho_outlook_residual import (
    evaluate_residual_evidence,
    write_residual_authority_request,
    write_residual_markdown,
)
from mlet.loader import load_site_series
from mlet.outlook.archive import build_eto_hindcast_archive, bundle_eto_hindcast_evidence
from mlet.outlook.build import build_outlook
from mlet.outlook.eto_build import build_eto_outlook_from_gefs
from mlet.outlook.eto_hindcast import (
    evaluate_eto_hindcast_evidence,
    write_eto_hindcast_json,
    write_eto_hindcast_markdown,
)
from mlet.outlook.hindcast import (
    evaluate_hindcast_evidence,
    write_hindcast_markdown,
    write_hindcast_validation,
    write_release_authority_request,
)
from mlet.outlook.publish import publish_outlook
from mlet.sources.gridmet import extract_eto
from mlet.sources.gefs import fetch_gefs, resolve_gefs_daily_artifact
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
    qc_eto = subparsers.add_parser(
        "qc-eto",
        help="Cross-check ASCE-PM and Priestley-Taylor reference ET on one weather member.",
    )
    qc_eto.add_argument("--member-json", required=True)
    qc_overlap = subparsers.add_parser(
        "qc-overlap",
        help="Measure forecast/observation ETo disagreement over a pre-issue-time window.",
    )
    qc_overlap.add_argument("--window-json", required=True)
    experiment = subparsers.add_parser("evaluate", help="Run the pre-registered Phase 2 experiment.")
    experiment.add_argument("--interim", required=True)
    experiment.add_argument("--landcover", required=True)
    experiment.add_argument("--out", required=True)
    experiment.add_argument("--result-json")
    experiment.add_argument("--data-manifest")
    experiment.add_argument("--git-revision")
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
    eto_hindcast = subparsers.add_parser(
        "hindcast-eto",
        help="Run the ETo-only, no-lookahead manuscript hindcast diagnostic.",
    )
    eto_hindcast.add_argument("--cases", required=True)
    eto_hindcast.add_argument("--out", required=True)
    build_eto = subparsers.add_parser(
        "build-eto",
        help="Build an ETo-only research candidate from a verified GEFS artifact.",
    )
    build_eto.add_argument("--artifact-pointer", required=True)
    build_eto.add_argument("--git-revision", required=True)
    build_eto.add_argument("--retrieved-at", required=True)
    build_eto.add_argument("--out", required=True)
    assemble_eto = subparsers.add_parser(
        "assemble-eto-evidence",
        help="Bundle verified ETo evidence directories below one archive root.",
    )
    assemble_eto.add_argument("--input", required=True, action="append")
    assemble_eto.add_argument("--out", required=True)
    build_eto_archive = subparsers.add_parser(
        "build-eto-hindcast-archive",
        help="Build a self-contained ETo hindcast archive from GEFS and AgriMet indexes.",
    )
    build_eto_archive.add_argument("--gefs-index")
    build_eto_archive.add_argument("--agrimet-index")
    build_eto_archive.add_argument("--input", action="append")
    build_eto_archive.add_argument("--out", "--destination", dest="destination", required=True)
    outlook = subparsers.add_parser(
        "outlook",
        help="Run the manuscript-scoped ETo outlook commands.",
    )
    outlook_subparsers = outlook.add_subparsers(
        dest="outlook_command", required=True
    )
    outlook_archive = outlook_subparsers.add_parser(
        "build-eto-hindcast-archive",
        help="Build a self-contained ETo hindcast archive from source indexes.",
    )
    outlook_archive.add_argument("--gefs-index", required=True)
    outlook_archive.add_argument("--agrimet-index", required=True)
    outlook_archive.add_argument("--destination", required=True)
    outlook_hindcast = outlook_subparsers.add_parser(
        "hindcast",
        help="Evaluate one schema-v4 ETo evidence archive.",
    )
    outlook_hindcast.add_argument("--evidence", required=True)
    outlook_hindcast.add_argument("--output", required=True)
    residual = subparsers.add_parser(
        "evaluate-outlook-residual",
        help="Run the frozen, non-serving Idaho outlook residual-model experiment.",
    )
    residual.add_argument("--cases", required=True)
    residual.add_argument("--out", required=True)
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
    if args.command == "qc-eto":
        return _run_qc_eto(args.member_json)
    if args.command == "qc-overlap":
        return _run_qc_overlap(args.window_json)
    if args.command == "fetch-outlook-inputs":
        return _run_fetch_outlook_inputs(args.issue_date, args.out)
    if args.command == "build-outlook":
        return _run_build_outlook(args.weather, args.state, args.crop, args.out)
    if args.command == "hindcast-outlook":
        return _run_hindcast_outlook(args.cases, args.out)
    if args.command == "hindcast-eto":
        return _run_hindcast_eto(args.cases, args.out)
    if args.command == "build-eto":
        return _run_build_eto(
            args.artifact_pointer,
            args.git_revision,
            args.retrieved_at,
            args.out,
        )
    if args.command == "assemble-eto-evidence":
        return _run_assemble_eto_evidence(args.input, args.out)
    if args.command == "build-eto-hindcast-archive":
        if args.gefs_index is not None or args.agrimet_index is not None:
            if args.gefs_index is None or args.agrimet_index is None:
                parser.error("--gefs-index and --agrimet-index must be supplied together")
            return _run_build_eto_hindcast_archive(
                args.gefs_index, args.agrimet_index, args.destination
            )
        if not args.input:
            parser.error("supply --gefs-index and --agrimet-index, or at least one --input")
        return _run_assemble_eto_evidence(args.input, args.destination)
    if args.command == "outlook":
        if args.outlook_command == "build-eto-hindcast-archive":
            return _run_build_eto_hindcast_archive(
                args.gefs_index, args.agrimet_index, args.destination
            )
        if args.outlook_command == "hindcast":
            return _run_hindcast_eto(args.evidence, args.output)
        raise AssertionError("unhandled outlook command")
    if args.command == "evaluate-outlook-residual":
        return _run_outlook_residual(args.cases, args.out)
    if args.command == "publish-outlook":
        return _run_publish_outlook(args.run, args.out)
    if args.result_json is not None and (
        args.data_manifest is None or args.git_revision is None
    ):
        parser.error("--result-json requires --data-manifest and --git-revision")
    result = phase2_openet_value.run(args.interim, args.landcover)
    _write_report(args.out, result)
    if args.result_json is not None:
        assert args.data_manifest is not None and args.git_revision is not None
        manifest_bytes = Path(args.data_manifest).read_bytes()
        record = phase2_openet_value.build_phase2_result_record(
            result,
            data_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            git_revision=args.git_revision,
        )
        _write_new_json(Path(args.result_json), record)
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


def _run_qc_eto(member_json: str) -> int:
    """Print the three-way reference-ET comparison for one weather member."""
    from datetime import datetime

    from mlet.outlook.contracts import WeatherMember
    from mlet.reference.priestley_taylor import compare_eto_implementations

    try:
        with open(member_json, encoding="utf-8") as handle:
            payload = json.load(handle)
        member = WeatherMember(
            grid_id=payload["grid_id"],
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            elevation_m=float(payload["elevation_m"]),
            member_id=payload["member_id"],
            issued_at=datetime.fromisoformat(payload["issued_at"]),
            valid_date=date.fromisoformat(payload["valid_date"]),
            tmax_c=float(payload["tmax_c"]),
            tmin_c=float(payload["tmin_c"]),
            vapor_pressure_kpa=float(payload["vapor_pressure_kpa"]),
            wind_m_s=float(payload["wind_m_s"]),
            solar_mj_m2_day=float(payload["solar_mj_m2_day"]),
            precip_mm=float(payload["precip_mm"]),
        )
        comparison = compare_eto_implementations(member)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot run qc-eto: {exc}", file=sys.stderr)
        return 2
    print(f"ASCE-PM (mlet)        : {comparison.asce_mlet_mm:.4f} mm/day")
    print(f"ASCE-PM (pyfao56)     : {comparison.asce_pyfao56_mm:.4f} mm/day")
    print(f"Priestley-Taylor      : {comparison.priestley_taylor_mm:.4f} mm/day")
    print(f"PT / ASCE-PM ratio    : {comparison.pt_over_asce_ratio:.4f}")
    if comparison.asce_mlet_mm != comparison.asce_pyfao56_mm:
        print("FAIL: shared-equation paths disagree")
        return 1
    if not comparison.within_documented_band:
        print("FAIL: PT / ASCE-PM ratio outside the documented 0.60-1.05 band")
        return 1
    print("ok: both paths agree and the ratio is inside the documented band")
    return 0


def _run_qc_overlap(window_json: str) -> int:
    """Print the forecast-overlap disagreement diagnostic for one window."""
    from datetime import datetime

    from mlet.outlook.contracts import WeatherMember
    from mlet.outlook.overlap import OverlapWindow, evaluate_overlap

    def _member(payload: dict) -> WeatherMember:
        return WeatherMember(
            grid_id=payload["grid_id"],
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            elevation_m=float(payload["elevation_m"]),
            member_id=payload["member_id"],
            issued_at=datetime.fromisoformat(payload["issued_at"]),
            valid_date=date.fromisoformat(payload["valid_date"]),
            tmax_c=float(payload["tmax_c"]),
            tmin_c=float(payload["tmin_c"]),
            vapor_pressure_kpa=float(payload["vapor_pressure_kpa"]),
            wind_m_s=float(payload["wind_m_s"]),
            solar_mj_m2_day=float(payload["solar_mj_m2_day"]),
            precip_mm=float(payload["precip_mm"]),
        )

    try:
        with open(window_json, encoding="utf-8") as handle:
            payload = json.load(handle)
        window = OverlapWindow(
            issue_time=datetime.fromisoformat(payload["issue_time"]),
            overlap_days=int(payload["overlap_days"]),
            observed=tuple(_member(row) for row in payload["observed"]),
            forecast=tuple(_member(row) for row in payload["forecast"]),
        )
        diagnostic = evaluate_overlap(window)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: cannot run qc-overlap: {exc}", file=sys.stderr)
        return 2
    print(f"overlap days            : {diagnostic.n_days}")
    print(f"mean abs difference     : {diagnostic.mean_absolute_difference_mm:.4f} mm/day")
    print(f"bias (forecast-observed): {diagnostic.bias_mm:+.4f} mm/day")
    print(f"max abs difference      : {diagnostic.max_absolute_difference_mm:.4f} mm/day")
    print(f"verdict               : {diagnostic.verdict}")
    return 0 if diagnostic.verdict == "consistent" else 1


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


def _run_hindcast_eto(cases_path: str, destination: str) -> int:
    """Write the ETo-only diagnostic and retain the external review boundary."""
    try:
        report_path = _trusted_hindcast_output(Path(destination))
        report = evaluate_eto_hindcast_evidence(Path(cases_path))
        write_eto_hindcast_markdown(report, report_path)
        write_eto_hindcast_json(report, report_path.with_suffix(".json"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot run ETo hindcast: {exc}", file=sys.stderr)
        return 2
    print(f"report: {report_path}")
    print(f"result: {report_path.with_suffix('.json')}")
    print("promotion: false")
    print("validation scope: eto_mm only")
    return 1


def _run_build_eto(
    artifact_pointer: str,
    git_revision: str,
    retrieved_at: str,
    destination: str,
) -> int:
    """Build an ETo candidate from one verified canonical GEFS pointer."""
    try:
        artifact_set = resolve_gefs_daily_artifact(Path(artifact_pointer))
        manifest = build_eto_outlook_from_gefs(
            artifact_set=artifact_set,
            git_revision=git_revision,
            retrieved_at=retrieved_at,
            destination=Path(destination),
        )
    except (OSError, ValueError, NotImplementedError) as exc:
        print(f"error: cannot build ETo candidate: {exc}", file=sys.stderr)
        return 2
    print(f"run_id: {manifest.run_id}")
    print("production_status: research_candidate")
    print("validation_status: evaluation_pending")
    return 0


def _run_assemble_eto_evidence(inputs: list[str], destination: str) -> int:
    """Bundle verified ETo cases without evaluating or promoting them."""
    try:
        evidence_path = bundle_eto_hindcast_evidence(
            tuple(Path(value) for value in inputs), Path(destination)
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot assemble ETo evidence: {exc}", file=sys.stderr)
        return 2
    print(f"evidence: {evidence_path}")
    print("validation_status: evaluation_pending")
    print("promotion: false")
    return 0


def _run_build_eto_hindcast_archive(
    gefs_index: str, agrimet_index: str, destination: str
) -> int:
    """Build and verify one ETo archive from two source indexes."""
    try:
        evidence_path = build_eto_hindcast_archive(
            Path(gefs_index), Path(agrimet_index), Path(destination)
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot build ETo hindcast archive: {exc}", file=sys.stderr)
        return 2
    print(f"evidence: {evidence_path}")
    print("validation_status: evaluation_pending")
    print("promotion: false")
    return 0


def _run_outlook_residual(cases_path: str, destination: str) -> int:
    """Write a permanently non-promotable ML research candidate."""
    try:
        report_path = _trusted_hindcast_output(Path(destination))
        report, receipt = evaluate_residual_evidence(Path(cases_path))
        authority_path = report_path.with_name(
            f"{report_path.stem}.authority_request.json"
        )
        if authority_path.exists() or authority_path.is_symlink():
            raise ValueError("residual authority request destination already exists")
        write_residual_markdown(report, report_path)
        write_residual_authority_request(receipt, authority_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot evaluate outlook residual experiment: {exc}", file=sys.stderr)
        return 2
    print(f"report: {report_path}")
    print(f"authority request: {authority_path}")
    print("promotion: false")
    print("external_release_eligible: false")
    print("status: non-serving research candidate")
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


def _write_new_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("Phase 2 result JSON output must not already exist")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("Phase 2 result JSON parent must be a real directory")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(f"{encoded}\n")
