"""Summarize the exploratory daily-gridMET stuck-wind correction."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/results/ml_tier1_gridmet_stuck_corrected"
ORIGINAL = ROOT / "docs/results/ml_tier1_gridmet_10member"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_GRIDMET_STUCK_CORRECTION_PROTOCOL.md"
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20260925
METHODS = ["OpenET", "Gain", "SupportGain", "MonoGain", "AugmentedGain"]
CONTRASTS = [
    ("wind_stuck_7_days", "SupportGain", "Gain"),
    ("wind_stuck_7_days", "MonoGain", "SupportGain"),
    ("wind_stuck_7_days", "AugmentedGain", "SupportGain"),
    ("clean", "AugmentedGain", "SupportGain"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def station_macro_mae(frame: pd.DataFrame, method: str) -> float:
    errors = np.abs(frame[method].to_numpy() - frame.y.to_numpy())
    station_errors = pd.DataFrame(
        {"station": frame.station.to_numpy(), "error": errors}
    ).groupby("station", sort=True).error.mean()
    return float(station_errors.mean())


def paired_group_interval(
    frame: pd.DataFrame, method: str, baseline: str, seed: int
) -> dict:
    paired = frame.assign(
        delta=np.abs(frame.y.to_numpy() - frame[baseline].to_numpy())
        - np.abs(frame.y.to_numpy() - frame[method].to_numpy())
    ).groupby(["group", "station"], sort=True).delta.mean().reset_index()
    groups = paired.groupby("group", sort=True).delta.agg(["sum", "count"])
    sums = groups["sum"].to_numpy()
    counts = groups["count"].to_numpy()
    rng = np.random.default_rng(seed)
    sampled = rng.integers(0, len(sums), size=(BOOTSTRAP_DRAWS, len(sums)))
    values = sums[sampled].sum(axis=1) / counts[sampled].sum(axis=1)
    low, high = np.quantile(values, [0.025, 0.975])
    return {
        "method": method,
        "baseline": baseline,
        "delta_macro_mae_favoring_method": float(paired.delta.mean()),
        "ci95": [float(low), float(high)],
        "groups": int(len(groups)),
        "stations": int(frame.station.nunique()),
        "rows": int(len(frame)),
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": seed,
    }


def main() -> None:
    run_receipt_path = OUT / "receipt.json"
    result_path = OUT / "results.json"
    if not run_receipt_path.is_file() or not result_path.is_file():
        raise RuntimeError("The corrected experiment is incomplete")
    receipt = json.loads(run_receipt_path.read_text())
    if receipt.get("stuck_correction", {}).get("exploratory") is not True:
        raise ValueError("The run receipt does not mark this result exploratory")

    summary = {"conditions": {}, "contrasts": []}
    for condition in ("clean", "wind_stuck_7_days"):
        frame = pd.read_csv(OUT / f"predictions_{condition}.csv")
        metrics = {}
        for method in METHODS:
            metrics[method] = {
                "station_macro_mae": station_macro_mae(frame, method),
                "station_macro_acceptance": (
                    float(frame.groupby("station")[f"accept_{method}"].mean().mean())
                    if f"accept_{method}" in frame
                    else None
                ),
            }
        summary["conditions"][condition] = {
            "rows": int(len(frame)),
            "stations": int(frame.station.nunique()),
            "groups": int(frame.group.nunique()),
            "methods": metrics,
        }

    for index, (condition, method, baseline) in enumerate(CONTRASTS):
        frame = pd.read_csv(OUT / f"predictions_{condition}.csv")
        summary["contrasts"].append(
            {
                "condition": condition,
                **paired_group_interval(frame, method, baseline, BOOTSTRAP_SEED + index),
            }
        )

    summary_path = OUT / "exploratory_analysis.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    audit = {
        "protocol_sha256": sha256(PROTOCOL),
        "analysis_script_sha256": sha256(Path(__file__)),
        "run_receipt_sha256": sha256(run_receipt_path),
        "results_sha256": sha256(result_path),
        "original_receipt_sha256": sha256(ORIGINAL / "receipt.json"),
        "analysis_sha256": sha256(summary_path),
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "one_sided_tests": False,
        "exploratory": True,
    }
    (OUT / "analysis_receipt.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({"analysis_receipt": audit, "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
