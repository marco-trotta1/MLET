#!/usr/bin/env python3
"""Build verified LaTeX claim macros for the MLET manuscript."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from mlet.outlook.eto_hindcast import evaluate_eto_hindcast_evidence


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE2_RESULT = REPO_ROOT / "docs" / "results" / "phase2_openet_value.json"
PHASE2_RECEIPT = (
    REPO_ROOT
    / "docs"
    / "results"
    / "phase2_openet_independent_reproduction_receipt.json"
)
FIGURE_DATA = REPO_ROOT / "manuscript" / "arxiv" / "figures" / "figure_data.json"
GEFS_FEASIBILITY = REPO_ROOT / "data" / "outlook" / "gefs_reforecast_20190703_feasibility.json"
AGRIMET_ACQUISITION = REPO_ROOT / "data" / "outlook" / "agrimet_historical_acquisition.json"
AGRIMET_REGISTRY = REPO_ROOT / "data" / "outlook" / "agrimet_station_registry.json"
ETO_EVIDENCE = REPO_ROOT / "data" / "outlook" / "eto_feasibility_archive" / "evidence.json"

COMMON_SAMPLE_COUNT = 7_923
COMMON_MODEL_NAMES = (
    "B1_CropCoefficient",
    "B2_WeatherRidge",
    "M1_OpenETDirect",
    "M2_OpenETRecal",
    "M3_OpenETRidge",
)
B0_MODEL_NAME = "B0_Persistence"
B0_SAMPLE_COUNT = 1_555
H2_SCOPE_LABEL = "H2: preregistered comparison"
PHASE2_SCOPE_LABEL = "station-held-out 10-fold evaluation"
GRID_SCOPE_LABEL = "common 0.5-degree GEFS grid-point subset"
QUANTILE_BAND_LABEL = "uncalibrated ensemble p10 to p90 quantile band"
EMPIRICAL_COVERAGE_LABEL = "empirical p10 to p90 coverage"
NOMINAL_COVERAGE_LABEL = "nominal p10 to p90 coverage target"
NOMINAL_COVERAGE_TARGET = 0.80


def _object(path: Path) -> dict[str, object]:
    """Load one JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected one JSON object in {path}")
    return value


def _model_by_name(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    """Return the Phase 2 model records by name."""
    field_withheld = payload.get("field_withheld")
    if not isinstance(field_withheld, dict):
        raise ValueError("The Phase 2 record lacks station-held-out model results")
    models = field_withheld.get("models")
    if not isinstance(models, list):
        raise ValueError("The Phase 2 record lacks model results")
    records: dict[str, dict[str, object]] = {}
    for model in models:
        if not isinstance(model, dict):
            raise ValueError("Every Phase 2 model result must be an object")
        name = model.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Every Phase 2 model result must have a name")
        if name in records:
            raise ValueError(f"The Phase 2 model result repeats {name}")
        records[name] = model
    return records


def _validate_phase2_models(models: dict[str, dict[str, object]]) -> None:
    """Validate model scope before making descriptive claims."""
    missing = [name for name in (*COMMON_MODEL_NAMES, B0_MODEL_NAME) if name not in models]
    if missing:
        raise ValueError(f"The Phase 2 result lacks model records: {', '.join(missing)}")
    b0_count = int(models[B0_MODEL_NAME]["sample_count"])
    if b0_count != B0_SAMPLE_COUNT:
        raise ValueError(
            f"B0 must use {B0_SAMPLE_COUNT:,} consecutive-day pairs, got {b0_count:,}"
        )
    for name in COMMON_MODEL_NAMES:
        sample_count = int(models[name]["sample_count"])
        if sample_count != COMMON_SAMPLE_COUNT:
            raise ValueError(
                f"The common-sample model {name} must use "
                f"{COMMON_SAMPLE_COUNT:,} rows, got {sample_count:,}"
            )
    m2_mae = float(models["M2_OpenETRecal"]["mae_mm"])
    common_mae = {
        name: float(models[name]["mae_mm"])
        for name in COMMON_MODEL_NAMES
    }
    if any(m2_mae >= value for name, value in common_mae.items() if name != "M2_OpenETRecal"):
        raise ValueError(
            "M2 must be the strict lowest-MAE model among the common-sample models"
        )


def _b0_scope_label(models: dict[str, dict[str, object]]) -> str:
    """Format the B0 scope label from the validated machine record."""
    return f"B0: {int(models[B0_MODEL_NAME]['sample_count']):,} consecutive-day pairs"


def _macro(name: str, value: str) -> str:
    """Format one immutable LaTeX macro."""
    return f"\\newcommand{{\\{name}}}{{{value}}}"


def _build_claims() -> list[str]:
    """Validate the evidence and return publication macros."""
    phase2 = _object(PHASE2_RESULT)
    receipt = _object(PHASE2_RECEIPT)
    figure_data = _object(FIGURE_DATA)
    gefs = _object(GEFS_FEASIBILITY)
    agrimet = _object(AGRIMET_ACQUISITION)
    registry = _object(AGRIMET_REGISTRY)
    models = _model_by_name(phase2)
    _validate_phase2_models(models)
    b0_scope_label = _b0_scope_label(models)
    h2 = phase2.get("h2")
    if not isinstance(h2, dict):
        raise ValueError("The Phase 2 record lacks the H2 result")
    ci95 = h2.get("ci95_mm")
    if not isinstance(ci95, list) or len(ci95) != 2:
        raise ValueError("The H2 result lacks a 95% interval")

    b2 = models["B2_WeatherRidge"]
    m2 = models["M2_OpenETRecal"]
    m3 = models["M3_OpenETRidge"]
    b2_mae = float(b2["mae_mm"])
    m2_mae = float(m2["mae_mm"])
    m3_mae = float(m3["mae_mm"])
    delta = float(h2["mae_delta_mm"])
    reduction = float(h2["mae_reduction_fraction"])
    if not math.isclose(b2_mae - m3_mae, delta, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("The H2 delta does not compare B2 with M3")
    if not math.isclose(delta / b2_mae, reduction, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("The H2 reduction does not match the delta")
    if not m2_mae < m3_mae:
        raise ValueError("M2 must remain the descriptive minimum")
    if int(b2["sample_count"]) != int(m3["sample_count"]):
        raise ValueError("The H2 arms must use a common sample")

    build_stats = receipt.get("build_stats")
    if not isinstance(build_stats, dict):
        raise ValueError("The reproduction receipt lacks build statistics")
    decode = gefs.get("decode")
    availability = gefs.get("availability")
    if not isinstance(decode, dict) or not isinstance(availability, dict):
        raise ValueError("The GEFS feasibility record lacks source counts")
    stations = registry.get("stations")
    if not isinstance(stations, list):
        raise ValueError("The AgriMet registry lacks stations")
    idaho_station_count = sum(
        1 for station in stations if isinstance(station, dict) and station.get("state") == "ID"
    )

    report = evaluate_eto_hindcast_evidence(ETO_EVIDENCE)
    metric = next(
        item for item in report.metrics if item.group == "season" and item.key == "JJA"
    )
    figure_feasibility = figure_data.get("boii_feasibility")
    if not isinstance(figure_feasibility, dict):
        raise ValueError("The figure data lacks the BOII feasibility result")
    if not math.isclose(
        float(figure_feasibility["mae_mm"]),
        metric.mae_mm,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("The figure and evaluator MAE values differ")
    if report.target_count != 20 or report.case_count != 1 or report.station_count != 1:
        raise ValueError("The feasibility evidence scope changed")
    if metric.bootstrap_cluster_count != 1:
        raise ValueError("The feasibility case must not imply an interval")

    macros = [
        _macro("JoinedRows", f"{int(build_stats['rows_written']):,}"),
        _macro("JoinedLabels", f"{int(build_stats['labeled_rows']):,}"),
        _macro("JoinedStations", f"{int(build_stats['stations']):,}"),
        _macro("PhaseTwoN", f"{int(b2['sample_count']):,}"),
        _macro("PhaseTwoStations", "85"),
        _macro("PersistenceN", f"{int(models['B0_Persistence']['sample_count']):,}"),
        _macro("BZeroMAE", f"{float(models['B0_Persistence']['mae_mm']):.3f}"),
        _macro("BZeroRMSE", f"{float(models['B0_Persistence']['rmse_mm']):.3f}"),
        _macro("BZeroBias", f"{float(models['B0_Persistence']['bias_mm']):.3f}"),
        _macro("BOneMAE", f"{float(models['B1_CropCoefficient']['mae_mm']):.3f}"),
        _macro("BOneRMSE", f"{float(models['B1_CropCoefficient']['rmse_mm']):.3f}"),
        _macro("BOneBias", f"{float(models['B1_CropCoefficient']['bias_mm']):.3f}"),
        _macro("BTwoMAE", f"{b2_mae:.3f}"),
        _macro("BTwoRMSE", f"{float(b2['rmse_mm']):.3f}"),
        _macro("BTwoBias", f"{float(b2['bias_mm']):.3f}"),
        _macro("MOneMAE", f"{float(models['M1_OpenETDirect']['mae_mm']):.3f}"),
        _macro("MOneRMSE", f"{float(models['M1_OpenETDirect']['rmse_mm']):.3f}"),
        _macro("MOneBias", f"{float(models['M1_OpenETDirect']['bias_mm']):.3f}"),
        _macro("MTwoMAE", f"{m2_mae:.3f}"),
        _macro("MTwoRMSE", f"{float(m2['rmse_mm']):.3f}"),
        _macro("MTwoBias", f"{float(m2['bias_mm']):.3f}"),
        _macro("MThreeMAE", f"{m3_mae:.3f}"),
        _macro("MThreeRMSE", f"{float(m3['rmse_mm']):.3f}"),
        _macro("MThreeBias", f"{float(m3['bias_mm']):.3f}"),
        _macro("HtwoDelta", f"{delta:.3f}"),
        _macro("HtwoReduction", f"{100.0 * reduction:.1f}"),
        _macro("HtwoCILow", f"{float(ci95[0]):.3f}"),
        _macro("HtwoCIHigh", f"{float(ci95[1]):.3f}"),
        _macro("BootstrapPhaseTwo", "2,000"),
        _macro("BootstrapETo", "1,000"),
        _macro("PhaseTwoScope", PHASE2_SCOPE_LABEL),
        _macro("BZeroScope", b0_scope_label),
        _macro("HtwoScope", H2_SCOPE_LABEL),
        _macro("GridSubsetLabel", GRID_SCOPE_LABEL),
        _macro("FeasibilityBandLabel", QUANTILE_BAND_LABEL),
        _macro("FeasibilityEmpiricalCoverageLabel", EMPIRICAL_COVERAGE_LABEL),
        _macro("FeasibilityNominalCoverageLabel", NOMINAL_COVERAGE_LABEL),
        _macro("FeasibilityEmpiricalCoverage", f"{metric.p10_p90_coverage:.2f}"),
        _macro("FeasibilityNominalCoverage", f"{NOMINAL_COVERAGE_TARGET:.2f}"),
        _macro("FeasibilityCoverageLabel", EMPIRICAL_COVERAGE_LABEL),
        _macro("GEFSObjects", f"{int(availability['available_object_count']):,}"),
        _macro("GEFSBytes", f"{int(availability['available_byte_count']):,}"),
        _macro("GEFSRows", f"{int(decode['row_count']):,}"),
        _macro("GEFSGrids", f"{int(decode['grid_count']):,}"),
        _macro("GEFSMembers", f"{int(decode['member_count']):,}"),
        _macro("GEFSValidDates", f"{int(decode['valid_date_count']):,}"),
        _macro("AgriMetRows", f"{int(agrimet['row_count']):,}"),
        _macro("AgriMetExclusions", f"{int(agrimet['exclusion_count']):,}"),
        _macro("AgriMetHistoricalStations", f"{int(agrimet['station_count']):,}"),
        _macro("AgriMetCurrentStations", f"{len(stations):,}"),
        _macro("AgriMetIdahoStations", f"{idaho_station_count:,}"),
        _macro("FeasibilityN", f"{report.target_count:,}"),
        _macro("FeasibilityCases", f"{report.case_count:,}"),
        _macro("FeasibilityStations", f"{report.station_count:,}"),
        _macro("FeasibilityMAE", f"{metric.mae_mm:.3f}"),
        _macro("FeasibilityRMSE", f"{metric.rmse_mm:.3f}"),
        _macro("FeasibilityBias", f"{metric.bias_mm:.3f}"),
        _macro("FeasibilityBaselineMAE", f"{metric.baseline_mae_mm:.3f}"),
        _macro("FeasibilityImprovement", f"{metric.mae_improvement_mm:.3f}"),
        _macro("FeasibilityCoverage", f"{metric.p10_p90_coverage:.2f}"),
        _macro("FeasibilityWidth", f"{metric.mean_interval_width_mm:.3f}"),
        _macro("FeasibilityPinball", f"{metric.mean_pinball_loss_mm:.3f}"),
        _macro("FeasibilityClusters", f"{metric.bootstrap_cluster_count:,}"),
        _macro("SupportCells", "400"),
        _macro("SupportMinimum", "30"),
        _macro("SupportMinimumTotal", "12,000"),
        _macro("PhaseTwoSeed", "20260713"),
        _macro("EToSeed", "20260731"),
    ]
    return macros


def main() -> int:
    """Write the generated claim file."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "% Generated by scripts/build_arxiv_claims.py. Do not edit by hand.",
        *_build_claims(),
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
