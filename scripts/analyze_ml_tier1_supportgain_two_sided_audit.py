"""Recheck the SupportGain audit with two-sided group sign-flip tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/results/ml_tier1_gridmet_10member"
OUT = ROOT / "docs/results/ml_tier1_supportgain_directional_audit"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_SUPPORTGAIN_TWO_SIDED_AUDIT_PROTOCOL.md"
DIRECTIONAL_RECEIPT = OUT / "analysis_receipt.json"
DIRECTIONAL_COMPARISONS = OUT / "comparisons.json"
COMPARISONS_PATH = OUT / "two_sided_comparisons.json"
RECEIPT_PATH = OUT / "two_sided_analysis_receipt.json"
SEED = 20260925
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
BASELINES = ["Gain", "MonoGain", "AugmentedGain"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def group_differences(frame: pd.DataFrame, baseline: str) -> tuple[
    float, np.ndarray, np.ndarray, int, int
]:
    station = frame.assign(
        delta=np.abs(frame.y - frame[baseline])
        - np.abs(frame.y - frame.SupportGain)
    ).groupby(["group", "station"], sort=True).delta.mean().reset_index()
    groups = station.groupby("group", sort=True).delta.agg(["sum", "count"])
    return (
        float(station.delta.mean()),
        groups["sum"].to_numpy(),
        groups["count"].to_numpy(),
        int(len(station)),
        int(len(groups)),
    )


def bootstrap_interval(
    group_sums: np.ndarray, group_counts: np.ndarray, seed: int
) -> list[float]:
    rng = np.random.default_rng(seed)
    indices = rng.integers(
        0, len(group_sums), size=(BOOTSTRAP_DRAWS, len(group_sums))
    )
    values = group_sums[indices].sum(axis=1) / group_counts[indices].sum(axis=1)
    low, high = np.quantile(values, [0.025, 0.975])
    return [float(low), float(high)]


def two_sided_signflip_p(group_sums: np.ndarray, seed: int) -> float:
    observed = float(group_sums.sum())
    rng = np.random.default_rng(seed)
    signs = rng.integers(0, 2, size=(SIGNFLIP_DRAWS, len(group_sums))) * 2 - 1
    null = signs @ group_sums
    return float(
        (np.count_nonzero(np.abs(null) >= abs(observed)) + 1)
        / (SIGNFLIP_DRAWS + 1)
    )


def holm_adjust(pvalues: list[float]) -> list[float]:
    order = np.argsort(pvalues)
    adjusted = [0.0] * len(pvalues)
    current = 0.0
    for rank, index in enumerate(order):
        current = max(current, min(1.0, (len(pvalues) - rank) * pvalues[index]))
        adjusted[index] = current
    return adjusted


def analyze() -> list[dict]:
    if COMPARISONS_PATH.exists() or RECEIPT_PATH.exists():
        raise RuntimeError("Refusing to overwrite completed two-sided results")
    directional_receipt = json.loads(DIRECTIONAL_RECEIPT.read_text())
    if sha256(DIRECTIONAL_COMPARISONS) != directional_receipt["comparisons_sha256"]:
        raise ValueError("Directional audit results do not match their receipt")
    prior_rows = json.loads(DIRECTIONAL_COMPARISONS.read_text())
    prior = {
        (row["baseline"], row["condition"]): row for row in prior_rows
    }
    if len(prior) != len(BASELINES) * len(CONDITIONS):
        raise ValueError("The directional audit does not contain 39 comparisons")

    input_hashes = {}
    rows = []
    for baseline in BASELINES:
        for condition in CONDITIONS:
            path = SOURCE / f"predictions_{condition}.csv"
            input_hashes[path.name] = sha256(path)
            frame = pd.read_csv(path)
            required = {"group", "station", "y", "SupportGain", baseline}
            missing = required.difference(frame.columns)
            if missing:
                raise ValueError(f"{path.name} is missing {sorted(missing)}")
            point, group_sums, group_counts, stations, groups = group_differences(
                frame, baseline
            )
            index = len(rows)
            previous = prior[(baseline, condition)]
            rows.append({
                "method": "SupportGain",
                "baseline": baseline,
                "condition": condition,
                "delta_macro_mae_favoring_supportgain": point,
                "ci95": bootstrap_interval(group_sums, group_counts, SEED + index),
                "groups": groups,
                "stations": stations,
                "rows": int(len(frame)),
                "original_one_sided_p": previous["one_sided_signflip_p"],
                "original_one_sided_holm_p": previous["holm_p"],
                "two_sided_signflip_p": two_sided_signflip_p(
                    group_sums, SEED + index
                ),
            })

    adjusted = holm_adjust([row["two_sided_signflip_p"] for row in rows])
    for row, value in zip(rows, adjusted, strict=True):
        row["two_sided_holm_p"] = value
    COMPARISONS_PATH.write_text(json.dumps(rows, indent=2) + "\n")

    receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "analysis_script_sha256": sha256(Path(__file__)),
        "source_run_receipt_sha256": sha256(SOURCE / "receipt.json"),
        "source_analysis_receipt_sha256": sha256(SOURCE / "analysis_receipt.json"),
        "directional_comparisons_sha256": sha256(DIRECTIONAL_COMPARISONS),
        "source_prediction_sha256": input_hashes,
        "comparisons_sha256": sha256(COMPARISONS_PATH),
        "comparison_count": len(rows),
        "holm_family": "all 39 two-sided SupportGain comparisons",
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed_base": SEED,
        "signflip_draws": SIGNFLIP_DRAWS,
        "signflip_seed_base": SEED,
        "status": "exploratory_post_outcome_two_sided_direction_agnostic",
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return rows


if __name__ == "__main__":
    analyze()
