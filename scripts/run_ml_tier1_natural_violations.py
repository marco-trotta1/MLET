"""Replay the fixed Tier 1 fit and score held-out invalid weather rows."""
from __future__ import annotations

import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits

import ml_selective_residual as selective
import ml_tier1_selective as prior
import ml_transfer_audit as audit


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/results/ml_tier1_natural_violations"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_NATURAL_VIOLATIONS_PROTOCOL.md"
CLEAN = ROOT / "docs/results/ml_tier1/cohort_clean.csv"
ORIGINAL = ROOT / "docs/results/ml_transfer/cohort.csv"
PHYSICAL_AUDIT = ROOT / "docs/results/ml_tier1/physical_audit_complete_weather.csv"
SPLITS = ROOT / "docs/results/ml_transfer/splits.json"
SAVED_CLEAN = ROOT / "docs/results/ml_tier1_selective/predictions_clean.csv"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_replay(replay: pd.DataFrame, saved: pd.DataFrame) -> float:
    replay = replay.sort_values("row_id").reset_index(drop=True)
    saved = saved.sort_values("row_id").reset_index(drop=True)
    if replay.row_id.duplicated().any() or not replay.row_id.equals(saved.row_id):
        raise ValueError("The clean replay row identifiers differ from the saved run")
    for name in ("accept_Gain", "accept_SupportGain"):
        if not replay[name].equals(saved[name]):
            raise ValueError(f"The clean replay acceptance differs for {name}")
    maximum = 0.0
    for name in ("OpenET", "Full", "Gain", "SupportGain", "correction", "spread", "support_distance", "predicted_gain"):
        difference = np.abs(replay[name].to_numpy() - saved[name].to_numpy())
        maximum = max(maximum, float(difference.max()))
        if not np.all(difference <= 1e-8):
            raise ValueError(f"The clean replay prediction differs for {name}")
    return maximum


def main() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise RuntimeError(f"Refusing to overwrite results in {OUT}")
    clean = pd.read_csv(CLEAN)
    original = pd.read_csv(ORIGINAL)
    physical = pd.read_csv(PHYSICAL_AUDIT)
    splits = [
        item for item in json.loads(SPLITS.read_text())
        if item["regime"] == "proximity"
    ]
    invalid_ids = set(physical.loc[~physical.valid, "row_id"])
    if len(invalid_ids) != 165 or not invalid_ids <= set(original.row_id):
        raise ValueError("The fixed invalid-row population changed")
    if invalid_ids & set(clean.row_id):
        raise ValueError("The clean training data contain invalid rows")

    replayed = []
    scored = []
    fold_records = []
    started = time.perf_counter()
    with threadpool_limits(limits=1):
        for split in splits:
            train = clean[clean.row_id.isin(split["train_row_ids"])]
            test = clean[clean.row_id.isin(split["test_row_ids"])]
            invalid = original[
                original.row_id.isin(split["test_row_ids"])
                & original.row_id.isin(invalid_ids)
            ]
            inner, augmented = prior.inner_training(train, split, audit.FEATURES)
            selectors = prior.fit_selectors(inner, augmented, audit.FEATURES)
            network, fit_record = selective.fit_ensemble(
                train[audit.FEATURES].to_numpy(),
                (train.y - train.openet).to_numpy(),
            )
            replayed.append(prior.infer(test, network, selectors, train, audit.FEATURES)["clean"])
            if not invalid.empty:
                scored.append(prior.infer(invalid, network, selectors, train, audit.FEATURES)["clean"])
            fold_records.append({
                "fold": split["fold"],
                "train_rows": len(train),
                "clean_test_rows": len(test),
                "invalid_test_rows": len(invalid),
                "inner_rows": len(inner),
                "outer_fit": fit_record,
            })
            print(f"proximity fold {split['fold']} replayed", flush=True)

    replay = pd.concat(replayed, ignore_index=True)
    maximum = check_replay(replay, pd.read_csv(SAVED_CLEAN))
    predictions = pd.concat(scored, ignore_index=True).sort_values("row_id")
    if predictions.row_id.duplicated().any() or set(predictions.row_id) != invalid_ids:
        raise ValueError("The invalid rows were not scored exactly once")
    attributes = physical.set_index("row_id")["failed_rules"]
    predictions["failed_rules"] = predictions.row_id.map(attributes)
    other = predictions[predictions.station.ne("manilacotton")]
    if len(other) != 133 or other.station.nunique() != 21 or other.group.nunique() != 17:
        raise ValueError("The fixed non-manilacotton population changed")

    OUT.mkdir(parents=True, exist_ok=True)
    prediction_path = OUT / "predictions_invalid.csv"
    predictions.to_csv(prediction_path, index=False)
    inputs = (PROTOCOL, CLEAN, ORIGINAL, PHYSICAL_AUDIT, SPLITS, SAVED_CLEAN)
    receipt = {
        "protocol_commit": "843d7b0",
        "protocol_sha256": sha256(PROTOCOL),
        "run_script_sha256": sha256(Path(__file__)),
        "prior_script_sha256": sha256(ROOT / "scripts/ml_tier1_selective.py"),
        "input_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in inputs},
        "predictions_sha256": sha256(prediction_path),
        "rows": len(predictions),
        "stations": int(predictions.station.nunique()),
        "groups": int(predictions.group.nunique()),
        "non_manilacotton_rows": len(other),
        "clean_replay_rows": len(replay),
        "clean_replay_max_abs_difference_mm_day": maximum,
        "fit_seconds": time.perf_counter() - started,
        "folds": fold_records,
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "platform": platform.platform(),
    }
    (OUT / "run_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Natural input violation replay complete.", flush=True)


if __name__ == "__main__":
    main()
