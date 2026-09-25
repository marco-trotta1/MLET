"""Summarize Tier 1 gridMET split and proximity sensitivity runs."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_ml_tier1_gridmet as tier1_analysis
import ml_transfer_audit as audit
import run_ml_tier1_gridmet_sensitivity as sensitivity_runner

OUT = ROOT / "docs/results/ml_tier1_gridmet_sensitivity"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_GRIDMET_SPLIT_PROXIMITY_PROTOCOL.md"
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20260924
CONDITIONS = tier1_analysis.CONDITIONS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prediction_frame(record: dict, condition: str) -> pd.DataFrame:
    run_path = ROOT / record["run_path"]
    path = run_path / f"predictions_{condition}.csv"
    if not path.exists():
        path = run_path / f"predictions_{condition}.csv.gz"
    if not path.exists():
        raise FileNotFoundError(f"Missing predictions for {condition}: {run_path}")
    frame = pd.read_csv(path, compression="infer")
    required = {"row_id", "test_year", "station", "group", "y", "Gain", "SupportGain"}
    if not required.issubset(frame.columns):
        raise ValueError(f"The {condition} predictions lack required columns")
    return frame


def verify_run(record: dict) -> None:
    run_path = ROOT / record["run_path"]
    cohort_path = ROOT / record["cohort_path"]
    if record["anchor"]:
        receipt_path = run_path / "receipt.json"
        receipt = json.loads(receipt_path.read_text())
        if sha256(receipt_path) != record["run_receipt_sha256"]:
            raise ValueError("The anchor receipt hash changed")
        if receipt["cohort_sha256"] != sha256(cohort_path):
            raise ValueError("The anchor cohort hash changed")
        expected_hashes = {
            condition: sha256(run_path / f"predictions_{condition}.csv")
            for condition in CONDITIONS
        }
    else:
        receipt_path = run_path / "sensitivity_run_receipt.json"
        receipt = json.loads(receipt_path.read_text())
        if receipt["protocol_sha256"] != sha256(PROTOCOL):
            raise ValueError("A sensitivity run uses a different protocol")
        if receipt["cohort_sha256"] != sha256(cohort_path):
            raise ValueError("A sensitivity run uses a different cohort")
        if receipt["run_receipt_sha256"] != sha256(run_path / "receipt.json"):
            raise ValueError("A sensitivity Tier 1 receipt hash changed")
        expected_hashes = receipt["compressed_predictions"]
    if expected_hashes != record["prediction_hashes"]:
        raise ValueError("The manifest prediction hashes do not match the run")
    for condition, expected_hash in expected_hashes.items():
        suffix = ".csv" if record["anchor"] else ".csv.gz"
        prediction_path = run_path / f"predictions_{condition}{suffix}"
        if sha256(prediction_path) != expected_hash:
            raise ValueError(f"A saved prediction hash changed: {prediction_path}")


def paired_contrast(frame: pd.DataFrame, record: dict, condition: str) -> dict:
    _, station = tier1_analysis.group_differences(
        frame, "SupportGain", "Gain"
    )
    groups = station.groupby("group", sort=True).delta.agg(["sum", "count"])
    bootstrap_seed = (
        BOOTSTRAP_SEED
        + 100 * int(record["threshold_km"])
        + int(record["seed_index"])
    )
    low, high = tier1_analysis.bootstrap_interval(
        groups["sum"].to_numpy(), groups["count"].to_numpy(), bootstrap_seed
    )
    return {
        "threshold_km": int(record["threshold_km"]),
        "seed_index": int(record["seed_index"]),
        "split_seed": int(record["split_seed"]),
        "anchor": bool(record["anchor"]),
        "condition": condition,
        "support_improvement_mm_day": float(station.delta.mean()),
        "ci95_low_mm_day": low,
        "ci95_high_mm_day": high,
        "stations": int(len(station)),
        "groups": int(len(groups)),
        "rows": int(len(frame)),
        "gain_station_macro_mae_mm_day": audit.macro_mae(
            frame.y.to_numpy(), frame.Gain.to_numpy(), frame.station.to_numpy()
        ),
        "support_station_macro_mae_mm_day": audit.macro_mae(
            frame.y.to_numpy(),
            frame.SupportGain.to_numpy(),
            frame.station.to_numpy(),
        ),
    }


def summarize(contrasts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (threshold, condition), frame in contrasts.groupby(
        ["threshold_km", "condition"], sort=True
    ):
        values = frame.support_improvement_mm_day.to_numpy()
        rows.append(
            {
                "threshold_km": int(threshold),
                "condition": condition,
                "seed_count": int(len(frame)),
                "mean_support_improvement_mm_day": float(values.mean()),
                "sd_across_seed_splits_mm_day": float(np.std(values, ddof=1)),
                "minimum_support_improvement_mm_day": float(values.min()),
                "maximum_support_improvement_mm_day": float(values.max()),
                "positive_seed_count": int(np.count_nonzero(values > 0)),
                "bootstrap_ci_above_zero_seed_count": int(
                    np.count_nonzero(frame.ci95_low_mm_day.to_numpy() > 0)
                ),
                "bootstrap_ci_below_zero_seed_count": int(
                    np.count_nonzero(frame.ci95_high_mm_day.to_numpy() < 0)
                ),
            }
        )
    return pd.DataFrame(rows)


def analyze() -> dict:
    if tier1_analysis.BOOTSTRAP_DRAWS != BOOTSTRAP_DRAWS:
        raise ValueError("The group bootstrap draw count differs from the protocol")
    manifest_path = OUT / "run_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("The sensitivity run manifest is missing")
    manifest = json.loads(manifest_path.read_text())
    if manifest["protocol_sha256"] != sha256(PROTOCOL):
        raise ValueError("The run manifest does not match the frozen protocol")
    if len(manifest["runs"]) != len(sensitivity_runner.THRESHOLDS_KM) * len(
        sensitivity_runner.SPLIT_SEEDS
    ):
        raise ValueError("The run manifest has an unexpected number of arms")
    if any(record["status"] != "complete" for record in manifest["runs"]):
        raise RuntimeError("The sensitivity run is incomplete")

    contrasts = []
    for record in manifest["runs"]:
        verify_run(record)
        for condition in CONDITIONS:
            frame = prediction_frame(record, condition)
            contrasts.append(paired_contrast(frame, record, condition))
    contrast_frame = pd.DataFrame(contrasts).sort_values(
        ["threshold_km", "seed_index", "condition"]
    )
    summary_frame = summarize(contrast_frame)
    contrast_path = OUT / "run_contrasts.csv"
    summary_path = OUT / "seed_summary.csv"
    contrast_frame.to_csv(contrast_path, index=False, float_format="%.10g")
    summary_frame.to_csv(summary_path, index=False, float_format="%.10g")
    receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "analysis_script_sha256": sha256(Path(__file__)),
        "runner_sha256": sha256(Path(sensitivity_runner.__file__)),
        "run_manifest_sha256": sha256(manifest_path),
        "run_count": int(len(manifest["runs"])),
        "condition_count": len(CONDITIONS),
        "contrast_count": len(contrast_frame),
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed_base": BOOTSTRAP_SEED,
        "contrast_sha256": sha256(contrast_path),
        "summary_sha256": sha256(summary_path),
        "interpretation": "seed summaries are descriptive and have no p-values",
    }
    receipt_path = OUT / "analysis_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == "__main__":
    analyze()
