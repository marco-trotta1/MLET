#!/usr/bin/env python3
"""Build evidence-bound figures for the MLET arXiv manuscript."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, ListedColormap
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch
import numpy as np

from mlet.outlook.eto_hindcast import EtoHindcastReport, evaluate_eto_hindcast_evidence
try:
    from scripts.build_arxiv_claims import (
        GRID_SCOPE_LABEL,
        NOMINAL_COVERAGE_LABEL,
        PHASE2_SCOPE_LABEL,
        QUANTILE_BAND_LABEL,
        _model_by_name,
        _validate_phase2_models,
    )
except ModuleNotFoundError as error:
    if error.name != "scripts":
        raise
    from build_arxiv_claims import (
        GRID_SCOPE_LABEL,
        NOMINAL_COVERAGE_LABEL,
        PHASE2_SCOPE_LABEL,
        QUANTILE_BAND_LABEL,
        _model_by_name,
        _validate_phase2_models,
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE2_RESULT = REPO_ROOT / "docs" / "results" / "phase2_openet_value.json"
FEASIBILITY_ROOT = REPO_ROOT / "data" / "outlook" / "eto_feasibility_archive"
FEASIBILITY_EVIDENCE = FEASIBILITY_ROOT / "evidence.json"

INK = "#171717"
MUTED = "#5b5b5b"
RULE = "#999999"
BLUE = "#6688a4"
TEAL = "#6c9d9a"
RED = "#b66a5b"
GOLD = "#d1992d"
PALE_BLUE = "#eef3f6"
PALE_TEAL = "#edf5f3"
PALE_RED = "#f7efed"
PALE_GOLD = "#faf5e8"

PHASE2_LABEL = PHASE2_SCOPE_LABEL
GRID_LABEL = GRID_SCOPE_LABEL


def _load_json(path: Path) -> dict[str, object]:
    """Load one JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected one JSON object in {path}")
    return value


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest for one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_archive_file(root: Path, value: object, label: str) -> Path:
    """Resolve one evidence path and keep it below the archive root."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative path")
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"{label} must be a relative path")
    try:
        candidate = (root / relative).resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{label} must name an existing file") from error
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} resolves outside the feasibility archive") from error
    if not candidate.is_file():
        raise ValueError(f"{label} must name an existing file")
    return candidate


def _resolve_feasibility_case_paths() -> tuple[str, Path, Path]:
    """Resolve the one forecast case and its target from the evidence record."""
    root = FEASIBILITY_ROOT.resolve(strict=True)
    evidence = _load_json(FEASIBILITY_EVIDENCE)
    cases = evidence.get("cases")
    if not isinstance(cases, list) or len(cases) != 1:
        raise ValueError("The feasibility evidence must contain exactly one case")
    case = cases[0]
    if not isinstance(case, dict):
        raise ValueError("The feasibility case must be an object")
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("The feasibility case must contain a case ID")
    forecast = case.get("forecast")
    target = case.get("target")
    if not isinstance(forecast, dict) or not isinstance(target, dict):
        raise ValueError("The feasibility case must contain forecast and target records")
    outlook_path = _resolve_archive_file(
        root, forecast.get("artifact_path"), "forecast artifact path"
    )
    target_path = _resolve_archive_file(root, target.get("path"), "target artifact path")
    return case_id, outlook_path, target_path


def _support_tensor_scope(report: EtoHindcastReport) -> tuple[str, int]:
    """Return active evaluated season-fold scope and observation count."""
    active: list[tuple[str, int, int]] = []
    for metric in report.metrics:
        if metric.group != "lead_season_spatial_fold" or metric.sample_count <= 0:
            continue
        parts = metric.key.split(":")
        if len(parts) != 3:
            raise ValueError("The evaluated support metric key is malformed")
        _lead_text, season, fold_text = parts
        active.append((season, int(fold_text), int(metric.sample_count)))
    if not active:
        raise ValueError("The evaluated support tensor has no observations")
    scopes = sorted({(season, fold) for season, fold, _count in active})
    scope_text = ", ".join(f"{season}-fold-{fold}" for season, fold in scopes)
    observation_count = sum(count for _season, _fold, count in active)
    return scope_text, observation_count


def _support_tensor_annotation(report: EtoHindcastReport) -> str:
    """Format the support note from evaluated support metrics."""
    scope_text, observation_count = _support_tensor_scope(report)
    return (
        f"The real feasibility archive supplies {observation_count} cell observations "
        f"across {scope_text}."
    )


def _configure_plot_style() -> None:
    """Match the locked manuscript prototype."""
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "font.size": 8.5,
            "axes.titlesize": 10,
            "axes.titleweight": "bold",
            "axes.labelsize": 8.5,
            "axes.edgecolor": INK,
            "axes.linewidth": 0.65,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7.5,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.04,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _save_figure(figure: plt.Figure, output_dir: Path, name: str) -> None:
    """Write one vector figure and one review image."""
    figure.savefig(output_dir / f"{name}.pdf")
    figure.savefig(output_dir / f"{name}.png", dpi=220)
    plt.close(figure)


def _box(
    axis: plt.Axes,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    subtitle: str,
    fill: str,
    stroke: str,
) -> None:
    """Draw one rounded evidence box."""
    axis.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.012,rounding_size=0.018",
            linewidth=0.9,
            edgecolor=stroke,
            facecolor=fill,
        )
    )
    axis.text(
        x + width / 2,
        y + height * 0.62,
        title,
        ha="center",
        va="center",
        color=INK,
        family="sans-serif",
        weight="bold",
        fontsize=8.2,
    )
    axis.text(
        x + width / 2,
        y + height * 0.28,
        subtitle,
        ha="center",
        va="center",
        color=MUTED,
        family="sans-serif",
        fontsize=7.0,
    )


def _arrow(
    axis: plt.Axes,
    *,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str,
) -> None:
    """Draw one thin evidence arrow."""
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="->",
            mutation_scale=9,
            linewidth=0.9,
            color=color,
        )
    )


def _figure_evidence_paths(output_dir: Path) -> None:
    """Build the target and evidence architecture."""
    models, h2 = _phase2_data()
    model_by_name = {str(model["name"]): model for model in models}
    b2_mae = float(model_by_name["B2_WeatherRidge"]["mae_mm"])
    m3_mae = float(model_by_name["M3_OpenETRidge"]["mae_mm"])
    delta = float(h2["mae_delta_mm"])
    reduction = float(h2["mae_reduction_fraction"])
    ci95 = h2["ci95_mm"]
    if not isinstance(ci95, list) or len(ci95) != 2:
        raise ValueError("Phase 2 H2 record must contain a paired interval")
    figure, axis = plt.subplots(figsize=(7.0, 3.05))
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.text(
        0.25,
        0.96,
        "Retrospective actual ET",
        ha="center",
        va="top",
        weight="bold",
        fontsize=10.2,
    )
    axis.text(
        0.75,
        0.96,
        "Prospective reference ETo",
        ha="center",
        va="top",
        weight="bold",
        fontsize=10.2,
    )
    axis.plot([0.5, 0.5], [0.13, 0.91], color=RULE, linewidth=0.7)

    left_boxes = [
        (0.08, 0.71, "OpenET and flux", "152 joined stations"),
        (0.08, 0.48, "Station-held-out 10-fold evaluation", "85 stations; 7,923 common rows"),
        (0.08, 0.25, "Preregistered M3 comparison", "station-blocked bootstrap"),
    ]
    right_boxes = [
        (0.58, 0.71, "GEFSv12 reforecast", "issue-time-valid ensemble weather"),
        (0.58, 0.48, "ASCE short-reference ETo", "p10, p50, p90; leads 1 to 20"),
        (0.58, 0.25, "USBR AgriMet ETos", "independent station target"),
    ]
    for x, y, title, subtitle in left_boxes:
        _box(
            axis,
            x=x,
            y=y,
            width=0.34,
            height=0.13,
            title=title,
            subtitle=subtitle,
            fill=PALE_RED,
            stroke=RED,
        )
    for x, y, title, subtitle in right_boxes:
        _box(
            axis,
            x=x,
            y=y,
            width=0.34,
            height=0.13,
            title=title,
            subtitle=subtitle,
            fill=PALE_BLUE,
            stroke=BLUE,
        )
    for x, color in ((0.25, RED), (0.75, BLUE)):
        _arrow(axis, start=(x, 0.71), end=(x, 0.62), color=color)
        _arrow(axis, start=(x, 0.48), end=(x, 0.39), color=color)

    axis.text(
        0.25,
        0.12,
        (
            f"M3: {m3_mae:.3f}; B2: {b2_mae:.3f} mm/day\n"
            f"{100.0 * reduction:.1f}% reduction; paired 95% CI\n"
            f"[{float(ci95[0]):.3f}, {float(ci95[1]):.3f}] mm/day"
        ),
        ha="center",
        va="center",
        color=RED,
        family="sans-serif",
        weight="bold",
        fontsize=6.7,
    )
    axis.text(
        0.75,
        0.12,
        "One real issue and one station\npass the source checks\nThe 400-cell gate remains incomplete",
        ha="center",
        va="center",
        color=MUTED,
        family="sans-serif",
        weight="bold",
        fontsize=6.7,
    )
    _save_figure(figure, output_dir, "figure_1_evidence_paths")


def _phase2_data() -> tuple[list[dict[str, object]], dict[str, object]]:
    """Return validated Phase 2 model and H2 records."""
    payload = _load_json(PHASE2_RESULT)
    field_withheld = payload.get("field_withheld")
    h2 = payload.get("h2")
    if not isinstance(field_withheld, dict) or not isinstance(h2, dict):
        raise ValueError("Phase 2 result does not contain required records")
    models = field_withheld.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("Phase 2 result does not contain model metrics")
    if any(not isinstance(model, dict) for model in models):
        raise ValueError("Phase 2 model metrics must be objects")
    typed_models = [model for model in models if isinstance(model, dict)]
    by_name = _model_by_name(payload)
    _validate_phase2_models(by_name)
    b2 = float(by_name["B2_WeatherRidge"]["mae_mm"])
    m3 = float(by_name["M3_OpenETRidge"]["mae_mm"])
    m2 = float(by_name["M2_OpenETRecal"]["mae_mm"])
    delta = float(h2["mae_delta_mm"])
    reduction = float(h2["mae_reduction_fraction"])
    if not math.isclose(b2 - m3, delta, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("The H2 delta must compare B2 with preregistered M3")
    if not math.isclose(delta / b2, reduction, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("The H2 reduction does not match the result record")
    if not m2 < m3:
        raise ValueError("M2 must remain the descriptive minimum MAE model")
    return typed_models, h2


def _figure_phase2_models(output_dir: Path) -> None:
    """Build the Phase 2 model comparison."""
    models, h2 = _phase2_data()
    delta = float(h2["mae_delta_mm"])
    reduction = float(h2["mae_reduction_fraction"])
    ci95 = h2.get("ci95_mm")
    if not isinstance(ci95, list) or len(ci95) != 2:
        raise ValueError("Phase 2 H2 record must contain a paired interval")
    names = [str(model["name"]) for model in models]
    labels = {
        "B0_Persistence": "B0 Persistence",
        "B1_CropCoefficient": "B1 Crop coefficient",
        "B2_WeatherRidge": "B2 Weather ridge",
        "M1_OpenETDirect": "M1 OpenET direct",
        "M2_OpenETRecal": "M2 OpenET recalibration",
        "M3_OpenETRidge": "M3 OpenET ridge",
    }
    values = [float(model["mae_mm"]) for model in models]
    sample_counts = [int(model["sample_count"]) for model in models]
    colors = [GOLD if name == "B0_Persistence" else BLUE if name.startswith("B") else RED for name in names]

    figure, axis = plt.subplots(figsize=(7.1, 3.4))
    y = np.arange(len(names))
    bars = axis.barh(y, values, color=colors, height=0.62, edgecolor="none")
    axis.set_yticks(y, [labels[name] for name in names])
    axis.invert_yaxis()
    axis.set_xlabel("Station-held-out 10-fold mean absolute error (mm/day)")
    axis.set_title(f"Phase 2 {PHASE2_LABEL}", pad=22)
    axis.set_xlim(0, 1.82)
    axis.xaxis.grid(True, color="#dddddd", linewidth=0.45)
    axis.set_axisbelow(True)
    for name, bar, value, count in zip(names, bars, values, sample_counts):
        highlighted = name in {"M2_OpenETRecal", "M3_OpenETRidge"}
        axis.text(
            value - 0.025 if highlighted else value + 0.025,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.3f}  (n={count:,})",
            va="center",
            ha="right" if highlighted else "left",
            family="sans-serif",
            fontsize=7.3,
            weight="bold" if highlighted else "normal",
            color="white" if highlighted else INK,
        )

    name_to_y = {name: index for index, name in enumerate(names)}
    b2_y = name_to_y["B2_WeatherRidge"]
    m3_y = name_to_y["M3_OpenETRidge"]
    m2_y = name_to_y["M2_OpenETRecal"]
    axis.annotate(
        (
            f"Preregistered H2 comparison: {100.0 * reduction:.1f}% lower MAE\n"
            f"paired delta {delta:.3f} mm/day\n"
            f"95% CI [{float(ci95[0]):.3f}, {float(ci95[1]):.3f}] mm/day"
        ),
        xy=(float(models[m3_y]["mae_mm"]), m3_y),
        xytext=(1.19, 4.58),
        arrowprops={
            "arrowstyle": "-|>",
            "color": RED,
            "linewidth": 1.0,
            "mutation_scale": 8.0,
            "shrinkA": 5.0,
            "shrinkB": 2.0,
        },
        ha="left",
        va="center",
        family="sans-serif",
        fontsize=7.4,
        color=RED,
    )
    axis.annotate(
        "Lowest descriptive MAE among common fitted models; H2 is a preregistered comparison",
        xy=(float(models[m2_y]["mae_mm"]), m2_y),
        xytext=(1.08, 3.65),
        arrowprops={
            "arrowstyle": "-|>",
            "color": MUTED,
            "linewidth": 1.0,
            "mutation_scale": 8.0,
            "shrinkA": 5.0,
            "shrinkB": 2.0,
        },
        ha="left",
        va="center",
        family="sans-serif",
        fontsize=7.2,
        color=MUTED,
    )
    by_name = {str(model["name"]): model for model in models}
    b0_count = int(by_name["B0_Persistence"]["sample_count"])
    common_count = int(by_name["B1_CropCoefficient"]["sample_count"])
    axis.text(
        0.0,
        1.01,
        (
            f"B0 uses {b0_count:,} consecutive-day pairs and is an oracle-like diagnostic. "
            f"All fitted models use {common_count:,} common rows from 85 stations."
        ),
        transform=axis.transAxes,
        ha="left",
        va="bottom",
        family="sans-serif",
        fontsize=7.2,
        color=MUTED,
    )
    figure.subplots_adjust(top=0.80)
    _save_figure(figure, output_dir, "figure_2_phase2_models")


def _feasibility_rows() -> list[dict[str, float | int | str]]:
    """Join the real BOII target with its mapped forecast quantiles."""
    _case_id, outlook_path, target_path = _resolve_feasibility_case_paths()
    outlook = _load_json(outlook_path)
    target = _load_json(target_path)
    values = target.get("values")
    collections = outlook.get("feature_collections")
    if not isinstance(values, list) or not isinstance(collections, list):
        raise ValueError("Feasibility artifacts do not contain target and forecast rows")
    targets_by_lead: dict[int, dict[str, object]] = {}
    for raw in values:
        if not isinstance(raw, dict):
            raise ValueError("Target rows must be objects")
        targets_by_lead[int(raw["lead_day"])] = raw
    rows: list[dict[str, float | int | str]] = []
    for raw_collection in collections:
        if not isinstance(raw_collection, dict):
            raise ValueError("Forecast collections must be objects")
        lead_day = int(raw_collection["lead_day"])
        target_row = targets_by_lead[lead_day]
        features = raw_collection.get("features")
        if not isinstance(features, list):
            raise ValueError("Forecast collections must contain features")
        feature = next(
            (
                item
                for item in features
                if isinstance(item, dict)
                and isinstance(item.get("properties"), dict)
                and item["properties"].get("grid_id") == target_row["grid_id"]
            ),
            None,
        )
        if not isinstance(feature, dict):
            raise ValueError("Target grid is missing from the candidate")
        properties = feature["properties"]
        assert isinstance(properties, dict)
        layers = properties["layers"]
        assert isinstance(layers, dict)
        quantiles = layers["eto_mm"]
        assert isinstance(quantiles, dict)
        rows.append(
            {
                "lead_day": lead_day,
                "valid_date": str(target_row["valid_date"]),
                "p10": float(quantiles["p10"]),
                "p50": float(quantiles["p50"]),
                "p90": float(quantiles["p90"]),
                "target_mm": float(target_row["target_mm"]),
                "baseline_mm": float(target_row["baseline_p50_mm"]),
                "grid_id": str(target_row["grid_id"]),
                "latitude": float(target_row["latitude"]),
                "longitude": float(target_row["longitude"]),
            }
        )
    if [int(row["lead_day"]) for row in rows] != list(range(1, 21)):
        raise ValueError("The feasibility case must contain leads 1 through 20")
    return rows


def _figure_feasibility_trajectory(output_dir: Path) -> None:
    """Build the real BOII feasibility trajectory."""
    rows = _feasibility_rows()
    report = evaluate_eto_hindcast_evidence(FEASIBILITY_EVIDENCE)
    metric = next(
        item for item in report.metrics if item.group == "season" and item.key == "JJA"
    )
    leads = np.array([int(row["lead_day"]) for row in rows])
    p10 = np.array([float(row["p10"]) for row in rows])
    p50 = np.array([float(row["p50"]) for row in rows])
    p90 = np.array([float(row["p90"]) for row in rows])
    target = np.array([float(row["target_mm"]) for row in rows])
    baseline = np.array([float(row["baseline_mm"]) for row in rows])

    figure, axis = plt.subplots(figsize=(7.0, 3.45))
    axis.fill_between(
        leads,
        p10,
        p90,
        color=PALE_BLUE,
        edgecolor=BLUE,
        linewidth=0.7,
        label=f"GEFS ETo {QUANTILE_BAND_LABEL}",
    )
    axis.plot(leads, p50, color=BLUE, linewidth=1.5, marker="o", markersize=2.8, label="GEFS ETo p50")
    axis.plot(leads, target, color=RED, linewidth=1.35, marker="s", markersize=2.6, label="AgriMet ETos target")
    axis.plot(leads, baseline, color=TEAL, linewidth=1.1, linestyle="--", marker=".", markersize=3.0, label="Prior-year day-of-year mean")
    axis.set_xlim(1, 20)
    axis.set_xticks([1, 5, 10, 15, 20])
    axis.set_xlabel("Lead day from the 2019-07-03 00Z GEFS issue")
    axis.set_ylabel("Reference ETo (mm/day)")
    axis.set_title("Real BOII feasibility case: forecast distribution, target, and climatology")
    axis.grid(True, color="#dddddd", linewidth=0.45)
    axis.set_axisbelow(True)
    axis.legend(loc="upper right", frameon=False, ncol=2)
    figure.text(
        0.075,
        0.025,
        (
            f"Diagnostic only: {report.case_count} issue, {report.station_count} station, "
            f"n={metric.sample_count} targets. "
            f"Forecast MAE {metric.mae_mm:.3f}; climatology MAE {metric.baseline_mae_mm:.3f} mm/day.\n"
            f"{NOMINAL_COVERAGE_LABEL} {metric.p10_p90_coverage:.2f}; "
            f"p10 to p90 mean width {metric.mean_interval_width_mm:.3f} mm/day. "
            "Support 20 < 30 and one bootstrap cluster, so no skill interval is identified."
        ),
        ha="left",
        va="bottom",
        family="sans-serif",
        fontsize=7.0,
        color=MUTED,
    )
    figure.subplots_adjust(left=0.08, right=0.99, top=0.88, bottom=0.25)
    _save_figure(figure, output_dir, "figure_3_boii_feasibility")


def _common_grid_ids() -> tuple[str, ...]:
    """Return the deterministic common grid-point subset across all leads."""
    _case_id, outlook_path, _target_path = _resolve_feasibility_case_paths()
    outlook = _load_json(outlook_path)
    collections = outlook.get("feature_collections")
    if not isinstance(collections, list) or not collections:
        raise ValueError("Forecast candidate lacks feature collections")
    common: set[str] | None = None
    for raw_collection in collections:
        if not isinstance(raw_collection, dict):
            raise ValueError("Forecast collections must be objects")
        features = raw_collection.get("features")
        if not isinstance(features, list):
            raise ValueError("Forecast collections must contain features")
        grid_ids: set[str] = set()
        for feature in features:
            if not isinstance(feature, dict):
                raise ValueError("Forecast features must be objects")
            properties = feature.get("properties")
            if not isinstance(properties, dict) or not isinstance(properties.get("grid_id"), str):
                raise ValueError("Forecast features must contain grid IDs")
            grid_ids.add(properties["grid_id"])
        common = grid_ids if common is None else common & grid_ids
    if common is None or len(common) != 195:
        raise ValueError("The candidate must contain 195 common GEFS grid points")
    return tuple(sorted(common))


def _spatial_collection(lead_day: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return coordinates and quantiles for one candidate lead."""
    _case_id, outlook_path, _target_path = _resolve_feasibility_case_paths()
    outlook = _load_json(outlook_path)
    collections = outlook.get("feature_collections")
    if not isinstance(collections, list):
        raise ValueError("Forecast candidate lacks feature collections")
    collection = next(
        (
            item
            for item in collections
            if isinstance(item, dict) and int(item.get("lead_day", 0)) == lead_day
        ),
        None,
    )
    if not isinstance(collection, dict) or not isinstance(collection.get("features"), list):
        raise ValueError(f"Forecast candidate lacks lead {lead_day}")
    common_grid_ids = set(_common_grid_ids())
    longitudes: list[float] = []
    latitudes: list[float] = []
    medians: list[float] = []
    widths: list[float] = []
    for feature in collection["features"]:
        if not isinstance(feature, dict):
            raise ValueError("Forecast features must be objects")
        geometry = feature["geometry"]
        properties = feature["properties"]
        assert isinstance(geometry, dict) and isinstance(properties, dict)
        if properties.get("grid_id") not in common_grid_ids:
            continue
        coordinates = geometry["coordinates"]
        assert isinstance(coordinates, list) and len(coordinates) == 2
        layers = properties["layers"]
        assert isinstance(layers, dict)
        quantiles = layers["eto_mm"]
        assert isinstance(quantiles, dict)
        longitudes.append(float(coordinates[0]))
        latitudes.append(float(coordinates[1]))
        p10 = float(quantiles["p10"])
        p50 = float(quantiles["p50"])
        p90 = float(quantiles["p90"])
        medians.append(p50)
        widths.append(p90 - p10)
    if len(medians) != 195:
        raise ValueError("The real candidate must contain 195 common GEFS grid points")
    return (
        np.asarray(longitudes),
        np.asarray(latitudes),
        np.asarray(medians),
        np.asarray(widths),
    )


def _figure_native_grid(output_dir: Path) -> None:
    """Build real candidate spatial snapshots."""
    lead_data = {lead: _spatial_collection(lead) for lead in (1, 10, 20)}
    all_medians = np.concatenate([lead_data[lead][2] for lead in lead_data])
    all_widths = np.concatenate([lead_data[lead][3] for lead in lead_data])
    median_limits = (float(all_medians.min()), float(all_medians.max()))
    width_limits = (float(all_widths.min()), float(all_widths.max()))
    eto_map = LinearSegmentedColormap.from_list("mlet_eto", [PALE_BLUE, BLUE, INK])
    width_map = LinearSegmentedColormap.from_list("mlet_width", [PALE_RED, RED, INK])
    figure, axes = plt.subplots(1, 4, figsize=(7.0, 3.0), sharex=True, sharey=True)
    station_longitude = float(_feasibility_rows()[0]["longitude"])
    station_latitude = float(_feasibility_rows()[0]["latitude"])
    median_artist = None
    for axis, lead in zip(axes[:3], (1, 10, 20)):
        longitude, latitude, median, _width = lead_data[lead]
        median_artist = axis.scatter(
            longitude,
            latitude,
            c=median,
            cmap=eto_map,
            vmin=median_limits[0],
            vmax=median_limits[1],
            marker="s",
            s=24,
            linewidths=0,
        )
        axis.scatter(
            [station_longitude],
            [station_latitude],
            marker="*",
            s=34,
            color=GOLD,
            edgecolor=INK,
            linewidth=0.4,
            zorder=3,
        )
        axis.set_title(f"p50, lead {lead}", fontsize=8.5)
    longitude, latitude, _median, width = lead_data[20]
    width_artist = axes[3].scatter(
        longitude,
        latitude,
        c=width,
        cmap=width_map,
        vmin=width_limits[0],
        vmax=width_limits[1],
        marker="s",
        s=24,
        linewidths=0,
    )
    axes[3].scatter(
        [station_longitude],
        [station_latitude],
        marker="*",
        s=34,
        color=GOLD,
        edgecolor=INK,
        linewidth=0.4,
        zorder=3,
    )
    axes[3].set_title("p90-p10, lead 20", fontsize=8.5)
    for axis in axes:
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlim(-117.25, -110.75)
        axis.set_ylim(41.75, 49.25)
        axis.set_xlabel("Longitude")
        axis.tick_params(length=2.2)
    axes[0].set_ylabel("Latitude")
    assert median_artist is not None
    median_color_axis = figure.add_axes([0.08, 0.16, 0.61, 0.022])
    median_bar = figure.colorbar(
        median_artist,
        cax=median_color_axis,
        orientation="horizontal",
    )
    median_bar.set_label("ETo p50 (mm/day)", fontsize=6.8, labelpad=1.5)
    median_bar.ax.tick_params(labelsize=6.3, length=1.8)
    width_color_axis = figure.add_axes([0.76, 0.16, 0.18, 0.022])
    width_bar = figure.colorbar(
        width_artist,
        cax=width_color_axis,
        orientation="horizontal",
    )
    width_bar.set_label("p90-p10 width (mm/day)", fontsize=6.8, labelpad=1.5)
    width_bar.ax.tick_params(labelsize=6.3, length=1.8)
    figure.suptitle(
        f"{GRID_LABEL} in the real 2019-07-03 research candidate",
        y=0.99,
        fontsize=10,
        weight="bold",
    )
    figure.text(
        0.5,
        0.02,
        "Each panel contains 195 points from the common 0.5-degree GEFS grid-point subset. The gold marker is BOII. The points are not field boundaries or area-weighted state estimates.",
        ha="center",
        va="bottom",
        family="sans-serif",
        fontsize=6.9,
        color=MUTED,
    )
    figure.subplots_adjust(top=0.82, bottom=0.32, left=0.06, right=0.98, wspace=0.12)
    _save_figure(figure, output_dir, "figure_4_native_grid")


def _figure_support_tensor(output_dir: Path) -> None:
    """Build the 400-cell evaluation support map."""
    report = evaluate_eto_hindcast_evidence(FEASIBILITY_EVIDENCE)
    matrix = np.zeros((20, 20), dtype=int)
    season_index = {season: index for index, season in enumerate(("DJF", "MAM", "JJA", "SON"))}
    for metric in report.metrics:
        if metric.group != "lead_season_spatial_fold":
            continue
        lead_text, season, fold_text = metric.key.split(":")
        row = season_index[season] * 5 + int(fold_text)
        matrix[row, int(lead_text) - 1] = metric.sample_count
    states = np.zeros_like(matrix)
    states[(matrix > 0) & (matrix < 30)] = 1
    states[matrix >= 30] = 2
    support_map = ListedColormap(["#eeeeee", RED, BLUE])
    figure, axis = plt.subplots(figsize=(7.0, 3.75))
    axis.imshow(states, aspect="auto", cmap=support_map, vmin=0, vmax=2, interpolation="nearest")
    labels = [f"{season}, fold {fold}" for season in ("DJF", "MAM", "JJA", "SON") for fold in range(5)]
    axis.set_yticks(np.arange(20), labels)
    axis.set_xticks(np.arange(20), [str(lead) for lead in range(1, 21)])
    axis.set_xlabel("Lead day")
    axis.set_ylabel("Held-out season and spatial fold")
    axis.set_title("Preregistered ETo support tensor: 20 leads by 4 seasons by 5 folds")
    axis.set_xticks(np.arange(-0.5, 20, 1), minor=True)
    axis.set_yticks(np.arange(-0.5, 20, 1), minor=True)
    axis.grid(which="minor", color="white", linewidth=0.6)
    axis.tick_params(which="minor", bottom=False, left=False)
    axis.spines.top.set_visible(True)
    axis.spines.right.set_visible(True)
    axis.legend(
        handles=[
            Patch(facecolor="#eeeeee", label="n=0"),
            Patch(facecolor=RED, label="0<n<30"),
            Patch(facecolor=BLUE, label="n>=30"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        ncol=3,
        frameon=False,
    )
    annotation = _support_tensor_annotation(report)
    figure.text(
        0.01,
        0.01,
        (
            f"{annotation} The frozen minimum is 12,000 cell observations "
            "(400 cells x 30)."
        ),
        ha="left",
        va="bottom",
        family="sans-serif",
        fontsize=7.0,
        color=MUTED,
    )
    figure.subplots_adjust(left=0.19, right=0.99, top=0.88, bottom=0.24)
    _save_figure(figure, output_dir, "figure_5_support_tensor")


def _write_figure_data(output_dir: Path) -> None:
    """Write the values and source digests used by the figures."""
    models, h2 = _phase2_data()
    rows = _feasibility_rows()
    report = evaluate_eto_hindcast_evidence(FEASIBILITY_EVIDENCE)
    _case_id, outlook_path, target_path = _resolve_feasibility_case_paths()
    _scope_text, feasibility_cell_observations = _support_tensor_scope(report)
    season_metric = next(
        item for item in report.metrics if item.group == "season" and item.key == "JJA"
    )
    payload = {
        "schema_version": 1,
        "kind": "mlet.arxiv-figure-data",
        "sources": {
            "phase2_result": {
                "path": str(PHASE2_RESULT.relative_to(REPO_ROOT)),
                "sha256": _sha256(PHASE2_RESULT),
            },
            "feasibility_evidence": {
                "path": str(FEASIBILITY_EVIDENCE.relative_to(REPO_ROOT)),
                "sha256": _sha256(FEASIBILITY_EVIDENCE),
                "evaluation_sha256": report.evaluation_sha256,
            },
            "feasibility_outlook": {
                "path": str(outlook_path.relative_to(REPO_ROOT)),
                "sha256": _sha256(outlook_path),
            },
            "feasibility_target": {
                "path": str(target_path.relative_to(REPO_ROOT)),
                "sha256": _sha256(target_path),
            },
        },
        "phase2": {"models": models, "h2": h2},
        "scope_labels": {
            "phase2": PHASE2_LABEL,
            "grid": GRID_LABEL,
            "quantile_band": QUANTILE_BAND_LABEL,
            "coverage": NOMINAL_COVERAGE_LABEL,
        },
        "boii_feasibility": {
            "rows": rows,
            "case_count": report.case_count,
            "station_count": report.station_count,
            "target_count": report.target_count,
            "mae_mm": season_metric.mae_mm,
            "baseline_mae_mm": season_metric.baseline_mae_mm,
            "coverage": season_metric.p10_p90_coverage,
            "mean_interval_width_mm": season_metric.mean_interval_width_mm,
            "mean_pinball_loss_mm": season_metric.mean_pinball_loss_mm,
            "bootstrap_cluster_count": season_metric.bootstrap_cluster_count,
            "completion_blocker_count": len(report.completion_blockers),
        },
        "support": {
            "cell_count": 400,
            "minimum_per_cell": 30,
            "minimum_cell_observations": 12_000,
            "feasibility_cell_observations": feasibility_cell_observations,
        },
    }
    (output_dir / "figure_data.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    """Build all manuscript figures."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.out.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _configure_plot_style()
    _figure_evidence_paths(output_dir)
    _figure_phase2_models(output_dir)
    _figure_feasibility_trajectory(output_dir)
    _figure_native_grid(output_dir)
    _figure_support_tensor(output_dir)
    _write_figure_data(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
