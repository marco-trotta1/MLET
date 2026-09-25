"""Run the predeclared paired tests for the all-station Tier 1 experiment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

OUT = ROOT / "docs/results/ml_tier1_gridmet_10member"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_GRIDMET_10MEMBER_PROTOCOL.md"
SEED = 20260924
BOOTSTRAP_DRAWS = 2000
SIGNFLIP_DRAWS = 20000

CONDITIONS = [
    "clean",
    "wind_x0",
    "wind_x0.447",
    "wind_x2.237",
    "wind_x3.6",
    "wind_x5",
    "wind_x10",
    "temperature_plus5",
    "temperature_plus10",
    "temperature_plus20",
    "temperature_plus32",
    "temperature_fahrenheit_as_celsius",
    "vpd_x10",
]

COMPARISONS = [
    (method, baseline, condition)
    for method, baseline in [
        ("Gain", "SupportGain"),
        ("MonoGain", "SupportGain"),
        ("AugmentedGain", "SupportGain"),
    ]
    for condition in CONDITIONS
] + [("LocalShrinkage", "Uniform", "clean")]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def group_differences(frame: pd.DataFrame, method: str, baseline: str) -> tuple[np.ndarray, pd.DataFrame]:
    station = frame.assign(
        delta=np.abs(frame.y - frame[baseline]) - np.abs(frame.y - frame[method])
    ).groupby(["group", "station"], sort=True).delta.mean().reset_index()
    groups = station.groupby("group", sort=True).delta.agg(["sum", "count"])
    return groups["sum"].to_numpy(), station


def bootstrap_interval(group_sums: np.ndarray, group_counts: np.ndarray, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    index = rng.integers(
        0, len(group_sums), size=(BOOTSTRAP_DRAWS, len(group_sums))
    )
    values = group_sums[index].sum(axis=1) / group_counts[index].sum(axis=1)
    low, high = np.quantile(values, [0.025, 0.975])
    return [float(low), float(high)]


def signflip_p(values: np.ndarray, seed: int) -> float:
    observed = float(values.sum())
    rng = np.random.default_rng(seed)
    signs = rng.integers(0, 2, size=(SIGNFLIP_DRAWS, len(values))) * 2 - 1
    null = signs @ values
    return float((np.count_nonzero(null >= observed) + 1) / (SIGNFLIP_DRAWS + 1))


def holm_adjust(pvalues: list[float]) -> list[float]:
    order = np.argsort(pvalues)
    adjusted = [0.0] * len(pvalues)
    current = 0.0
    for rank, index in enumerate(order):
        current = max(current, min(1.0, (len(pvalues) - rank) * pvalues[index]))
        adjusted[index] = current
    return adjusted


def analyze() -> list[dict]:
    if not (OUT / "results.json").exists() or not (OUT / "receipt.json").exists():
        raise RuntimeError("The fixed all-station experiment is incomplete")
    rows = []
    for index, (method, baseline, condition) in enumerate(COMPARISONS):
        frame = pd.read_csv(OUT / f"predictions_{condition}.csv")
        group_sums, station = group_differences(frame, method, baseline)
        groups = station.groupby("group", sort=True).delta.agg(["sum", "count"])
        rows.append(
            {
                "method": method,
                "baseline": baseline,
                "condition": condition,
                "delta_macro_mae_favoring_method": float(station.delta.mean()),
                "ci95": bootstrap_interval(
                    groups["sum"].to_numpy(), groups["count"].to_numpy(), SEED
                ),
                "groups": int(len(groups)),
                "stations": int(len(station)),
                "rows": int(len(frame)),
                "one_sided_signflip_p": signflip_p(group_sums, SEED + index),
            }
        )
    adjusted = holm_adjust([row["one_sided_signflip_p"] for row in rows])
    for row, value in zip(rows, adjusted):
        row["holm_p"] = value
    target = OUT / "primary_comparisons.json"
    target.write_text(json.dumps(rows, indent=2) + chr(10))
    analysis_receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "analysis_script_sha256": sha256(Path(__file__)),
        "results_sha256": sha256(OUT / "results.json"),
        "run_receipt_sha256": sha256(OUT / "receipt.json"),
        "primary_comparisons_sha256": sha256(target),
        "comparison_count": len(rows),
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": SEED,
        "signflip_draws": SIGNFLIP_DRAWS,
        "signflip_seed_base": SEED,
        "holm_family": "all comparisons in primary_comparisons.json",
    }
    (OUT / "analysis_receipt.json").write_text(
        json.dumps(analysis_receipt, indent=2) + chr(10)
    )
    print(json.dumps(analysis_receipt, indent=2))
    return rows


if __name__ == "__main__":
    analyze()
