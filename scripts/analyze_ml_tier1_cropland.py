"""Analyze the frozen cropland-only training comparison."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/results/ml_tier1_cropland"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_CROPLAND_TRAINING_PROTOCOL.md"
FULL_AUDIT_PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_CROPLAND_FULL_AUDIT.md"
PREDICTIONS = OUT / "predictions_cropland_test.csv"
RUN_RECEIPT = OUT / "run_receipt.json"
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20261005
FULL_AUDIT_BOOTSTRAP_SEED = 20261006
SYSTEMS = [
    ("OpenET", "openet", None),
    ("AllStationFull", "AllStationFull", None),
    ("AllStationSupportGain", "AllStationSupportGain", "accept_AllStationSupportGain"),
    ("CroplandOnlyFull", "CroplandOnlyFull", None),
    ("CroplandOnlySupportGain", "CroplandOnlySupportGain", "accept_CroplandOnlySupportGain"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def system_summary(frame: pd.DataFrame, name: str, prediction: str, acceptance: str | None) -> dict:
    error = np.abs(frame[prediction].to_numpy(dtype=float) - frame.y.to_numpy(dtype=float))
    weights = 1.0 / frame.groupby("station").row_id.transform("count").to_numpy(dtype=float)
    summary = {
        "system": name,
        "rows": int(len(frame)),
        "stations": int(frame.station.nunique()),
        "groups": int(frame.group.nunique()),
        "station_macro_mae_mm_day": float(np.average(error, weights=weights)),
        "pooled_mae_mm_day": float(error.mean()),
    }
    if acceptance is not None:
        summary["station_weighted_acceptance"] = float(
            frame.groupby("station")[acceptance].mean().mean()
        )
        summary["accepted_rows"] = int(frame[acceptance].sum())
    return summary


def paired_group_bootstrap(frame: pd.DataFrame) -> dict:
    station = frame.assign(
        delta=(
            np.abs(frame.y - frame.AllStationSupportGain)
            - np.abs(frame.y - frame.CroplandOnlySupportGain)
        )
    ).groupby(["group", "station"], sort=True).delta.mean().reset_index()
    groups = station.groupby("group", sort=True).delta.agg(["sum", "count"])
    point = float(station.delta.mean())
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    indices = rng.integers(
        0, len(groups), size=(BOOTSTRAP_DRAWS, len(groups))
    )
    values = (
        groups["sum"].to_numpy()[indices].sum(axis=1)
        / groups["count"].to_numpy()[indices].sum(axis=1)
    )
    low, high = np.quantile(values, [0.025, 0.975])
    return {
        "outcome": "all-station SupportGain MAE minus cropland-only SupportGain MAE",
        "positive_favors": "cropland-only training",
        "difference_mm_day": point,
        "ci95_mm_day": [float(low), float(high)],
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "rows": int(len(frame)),
        "stations": int(frame.station.nunique()),
        "groups": int(frame.group.nunique()),
    }


def exploratory_full_group_bootstrap(frame: pd.DataFrame) -> dict:
    """Estimate group uncertainty for the reviewed Full-model contrast."""
    station = frame.assign(
        delta=(
            np.abs(frame.y - frame.AllStationFull)
            - np.abs(frame.y - frame.CroplandOnlyFull)
        )
    ).groupby(["group", "station"], sort=True).delta.mean().reset_index()
    groups = station.groupby("group", sort=True).delta.agg(["sum", "count"])
    point = float(station.delta.mean())
    rng = np.random.default_rng(FULL_AUDIT_BOOTSTRAP_SEED)
    indices = rng.integers(
        0, len(groups), size=(BOOTSTRAP_DRAWS, len(groups))
    )
    values = (
        groups["sum"].to_numpy()[indices].sum(axis=1)
        / groups["count"].to_numpy()[indices].sum(axis=1)
    )
    low, high = np.quantile(values, [0.025, 0.975])
    return {
        "status": "exploratory_post_hoc",
        "outcome": "all-station Full MAE minus cropland-only Full MAE",
        "positive_favors": "cropland-only training",
        "difference_mm_day": point,
        "ci95_mm_day": [float(low), float(high)],
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": FULL_AUDIT_BOOTSTRAP_SEED,
        "rows": int(len(frame)),
        "stations": int(frame.station.nunique()),
        "groups": int(frame.group.nunique()),
        "p_value": None,
        "limitation": (
            "Point estimates were reviewed before this interval was defined. "
            "It conditions on fitted models and is not independent confirmation."
        ),
    }


def analyze() -> dict:
    if (
        not PREDICTIONS.is_file()
        or not RUN_RECEIPT.is_file()
        or not FULL_AUDIT_PROTOCOL.is_file()
    ):
        raise RuntimeError("The cropland-only model run is incomplete")
    frame = pd.read_csv(PREDICTIONS, parse_dates=["date"])
    run_receipt = json.loads(RUN_RECEIPT.read_text())
    if run_receipt["predictions_sha256"] != sha256(PREDICTIONS):
        raise ValueError("Cropland predictions do not match their run receipt")
    if len(frame) != run_receipt["rows"] or frame.row_id.duplicated().any():
        raise ValueError("Cropland predictions have invalid row identifiers")
    if frame["landcover"].ne("Croplands").any():
        raise ValueError("The prediction file contains a non-cropland row")

    metric_rows = []
    for label, subset in [("all_test_years", frame), *[(str(year), frame[frame.test_year == year]) for year in sorted(frame.test_year.unique())]]:
        for name, prediction, acceptance in SYSTEMS:
            metric_rows.append({"period": label, **system_summary(subset, name, prediction, acceptance)})
    metrics_path = OUT / "performance_summary.csv"
    pd.DataFrame(metric_rows).to_csv(metrics_path, index=False)
    primary = paired_group_bootstrap(frame)
    primary_path = OUT / "primary_comparison.json"
    primary_path.write_text(json.dumps(primary, indent=2) + "\n")
    secondary = exploratory_full_group_bootstrap(frame)
    secondary_path = OUT / "full_exploratory_comparison.json"
    secondary_path.write_text(json.dumps(secondary, indent=2) + "\n")
    receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "analysis_script_sha256": sha256(Path(__file__)),
        "run_receipt_sha256": sha256(RUN_RECEIPT),
        "predictions_sha256": sha256(PREDICTIONS),
        "primary_comparison_sha256": sha256(primary_path),
        "full_audit_protocol_sha256": sha256(FULL_AUDIT_PROTOCOL),
        "full_exploratory_comparison_sha256": sha256(secondary_path),
        "performance_summary_sha256": sha256(metrics_path),
        "primary_bootstrap_draws": BOOTSTRAP_DRAWS,
        "primary_bootstrap_seed": BOOTSTRAP_SEED,
        "primary_comparison": primary,
        "full_exploratory_comparison": secondary,
        "secondary_comparisons": "Descriptive. No p-values.",
    }
    receipt_path = OUT / "analysis_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == "__main__":
    analyze()
