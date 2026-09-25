"""Run the measured-weather selector feature correction."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ml_selective_residual as selective
import ml_tier1_selective as experiment

OUT = ROOT / "docs/results/ml_tier1_selective_corrected"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_SELECTIVE_CORRECTION_PROTOCOL.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corrected_inner_training(
    train: pd.DataFrame, split: dict, columns: list[str]
) -> tuple[pd.DataFrame, list[tuple]]:
    frames = []
    augmented = []
    for part_index, part in enumerate(split["inner_partitions"]):
        fit = train[train.row_id.isin(part["train_row_ids"])]
        validation = train[train.row_id.isin(part["validation_row_ids"])]
        if fit.empty or validation.empty:
            continue

        network, _ = selective.fit_ensemble(
            fit[columns].to_numpy(), (fit.y - fit.openet).to_numpy()
        )
        inputs = validation[columns].to_numpy()
        mean, spread, distance, _ = network.predict(inputs)
        inner = validation.copy()
        inner["correction"] = mean
        inner["spread"] = spread
        inner["distance"] = distance
        inner["gain"] = selective.improvement(
            validation.y.to_numpy(), validation.openet.to_numpy(), mean
        )
        inner["part"] = part_index
        frames.append(inner)

        variants = experiment.fault_inputs(validation, inputs, fit, columns)
        fault_names = [name for name in variants if name != "clean"]
        rng = np.random.default_rng(
            experiment.FAULT_SEED + int(split["fold"]) * 10 + part_index
        )
        assignment = rng.integers(0, len(fault_names), len(validation))
        augmented_inputs = np.empty_like(inputs)
        augmented_correction = np.empty(len(validation))
        augmented_spread = np.empty(len(validation))
        augmented_distance = np.empty(len(validation))
        for index, name in enumerate(fault_names):
            selected = assignment == index
            if not selected.any():
                continue
            transformed = variants[name][selected]
            augmented_inputs[selected] = transformed
            (
                augmented_correction[selected],
                augmented_spread[selected],
                augmented_distance[selected],
                _,
            ) = network.predict(transformed)

        augmented_features = selective.selector_features(
            augmented_correction,
            augmented_spread,
            augmented_distance,
            augmented_inputs,
        )
        augmented_gain = selective.improvement(
            validation.y.to_numpy(),
            validation.openet.to_numpy(),
            augmented_correction,
        )
        augmented.append(
            (augmented_features, augmented_gain, validation.station.to_numpy())
        )
    return pd.concat(frames).sort_values("row_id"), augmented


def main() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise RuntimeError(f"Refusing to overwrite results in {OUT}")
    if not PROTOCOL.is_file():
        raise FileNotFoundError(PROTOCOL)

    OUT.mkdir(parents=True, exist_ok=True)
    experiment.OUT = OUT
    experiment.inner_training = corrected_inner_training
    with threadpool_limits(limits=1):
        experiment.main()

    receipt_path = OUT / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    original_code_hash = receipt["code_sha256"]
    original_protocol_hash = receipt["protocol_sha256"]
    receipt["protocol_sha256"] = sha256(PROTOCOL)
    receipt["original_protocol_sha256"] = original_protocol_hash
    receipt["original_runner_sha256"] = original_code_hash
    receipt["correction_runner_sha256"] = sha256(Path(__file__))
    receipt["dependency_sha256"] = {
        "ml_tier1_selective.py": sha256(ROOT / "scripts/ml_tier1_selective.py"),
        "ml_selective_residual.py": sha256(ROOT / "scripts/ml_selective_residual.py"),
    }
    receipt["correction"] = (
        "Recomputed correction, spread, and support distance for each "
        "transformed inner-validation input."
    )
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
