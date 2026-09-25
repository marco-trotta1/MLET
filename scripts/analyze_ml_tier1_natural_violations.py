"""Summarize the fixed natural input violation replay."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/results/ml_tier1_natural_violations"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_NATURAL_VIOLATIONS_PROTOCOL.md"
PREDICTIONS = OUT / "predictions_invalid.csv"
RUN_RECEIPT = OUT / "run_receipt.json"
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20260924
METHODS = ("OpenET", "Full", "Gain", "SupportGain")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def population_metrics(frame: pd.DataFrame) -> dict:
    result = {
        "rows": len(frame),
        "stations": int(frame.station.nunique()),
        "groups": int(frame.group.nunique()),
        "methods": {},
    }
    for method in METHODS:
        station_error = (
            frame.assign(error=np.abs(frame.y - frame[method]))
            .groupby("station", sort=True).error.mean()
        )
        metrics = {
            "station_macro_mae_mm_day": float(station_error.mean()),
            "pooled_mae_mm_day": float(np.abs(frame.y - frame[method]).mean()),
        }
        acceptance = f"accept_{method}"
        if acceptance in frame:
            metrics["station_weighted_acceptance"] = float(
                frame.groupby("station", sort=True)[acceptance].mean().mean()
            )
        result["methods"][method] = metrics
    return result


def group_effects(frame: pd.DataFrame) -> pd.DataFrame:
    stations = (
        frame.assign(
            delta=np.abs(frame.y - frame.Gain)
            - np.abs(frame.y - frame.SupportGain)
        )
        .groupby(["group", "station"], sort=True)
        .agg(station_delta_mm_day=("delta", "mean"), rows=("row_id", "size"))
        .reset_index()
    )
    return (
        stations.groupby("group", sort=True)
        .agg(
            mean_station_delta_mm_day=("station_delta_mm_day", "mean"),
            sum_station_delta_mm_day=("station_delta_mm_day", "sum"),
            stations=("station", "size"),
            rows=("rows", "sum"),
        )
        .reset_index()
    )


def primary_comparison(frame: pd.DataFrame, effects: pd.DataFrame) -> dict:
    groups = effects.sort_values("group")
    sums = groups.sum_station_delta_mm_day.to_numpy()
    counts = groups.stations.to_numpy()
    point = float(sums.sum() / counts.sum())
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    indices = rng.integers(0, len(groups), size=(BOOTSTRAP_DRAWS, len(groups)))
    draws = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
    low, high = np.quantile(draws, [0.025, 0.975])
    return {
        "outcome": "Gain MAE minus SupportGain MAE",
        "positive_favors": "SupportGain",
        "station_macro_difference_mm_day": point,
        "ci95_mm_day": [float(low), float(high)],
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "rows": len(frame),
        "stations": int(frame.station.nunique()),
        "groups": len(groups),
        "groups_favor_supportgain": int((groups.mean_station_delta_mm_day > 0).sum()),
        "conditional_on_fixed_models": True,
        "exploratory": True,
    }


def main() -> None:
    for path in (PREDICTIONS, RUN_RECEIPT):
        if not path.is_file():
            raise RuntimeError(f"The replay input is missing: {path}")
    if (OUT / "analysis_receipt.json").exists():
        raise RuntimeError("Refusing to overwrite the completed analysis")
    receipt = json.loads(RUN_RECEIPT.read_text())
    if receipt["protocol_sha256"] != sha256(PROTOCOL):
        raise ValueError("The frozen protocol changed")
    if receipt["predictions_sha256"] != sha256(PREDICTIONS):
        raise ValueError("The saved predictions changed")
    frame = pd.read_csv(PREDICTIONS)
    if len(frame) != 165 or frame.row_id.duplicated().any():
        raise ValueError("The invalid prediction population changed")
    other = frame[frame.station.ne("manilacotton")]
    if (len(other), other.station.nunique(), other.group.nunique()) != (133, 21, 17):
        raise ValueError("The named comparison population changed")
    negative_vapor = frame.failed_rules.str.contains("actual_vapor_pressure", regex=False)
    populations = {
        "other_invalid": other,
        "all_invalid": frame,
        "manilacotton": frame[frame.station.eq("manilacotton")],
        "negative_vapor": frame[negative_vapor],
        "negative_vapor_other": other[
            other.failed_rules.str.contains("actual_vapor_pressure", regex=False)
        ],
    }
    effects = group_effects(other)
    group_path = OUT / "group_effects_other.csv"
    effects.to_csv(group_path, index=False)
    summary = {
        "primary_comparison": primary_comparison(other, effects),
        "populations": {
            name: population_metrics(subset)
            for name, subset in populations.items()
        },
        "secondary_results": "Descriptive. No p-values or planned intervals.",
    }
    summary_path = OUT / "analysis_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    analysis_receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "analysis_script_sha256": sha256(Path(__file__)),
        "run_receipt_sha256": sha256(RUN_RECEIPT),
        "predictions_sha256": sha256(PREDICTIONS),
        "group_effects_sha256": sha256(group_path),
        "analysis_summary_sha256": sha256(summary_path),
    }
    (OUT / "analysis_receipt.json").write_text(json.dumps(analysis_receipt, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
