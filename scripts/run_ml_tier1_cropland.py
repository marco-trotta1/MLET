"""Fit cropland-only Tier 1 models on the frozen rolling splits."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ml_selective_residual as selective
import ml_tier1_gridmet as tier1_runner
import ml_tier1_selective as tier1_selective
import ml_tier3_gridmet as tier3_runner
import ml_transfer_audit as audit

OUT = ROOT / "docs/results/ml_tier1_cropland"
COHORT = ROOT / "docs/results/ml_tier1_gridmet/cohort.csv"
SPLITS = ROOT / "docs/results/ml_tier1_gridmet_10member/splits.json"
BASE = ROOT / "docs/results/ml_tier1_gridmet_10member"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_CROPLAND_TRAINING_PROTOCOL.md"
BASE_RECEIPT = BASE / "receipt.json"
BASE_PREDICTIONS = BASE / "predictions_clean.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run() -> dict:
    if OUT.exists() and any(OUT.iterdir()):
        raise RuntimeError(f"Refusing to overwrite existing results in {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    cohort = pd.read_csv(COHORT, parse_dates=["date"])
    crop = cohort[cohort.landcover == "Croplands"].copy()
    split_records = json.loads(SPLITS.read_text())
    split_by_year = {int(record["test_year"]): record for record in split_records}
    baseline = pd.read_csv(BASE_PREDICTIONS)
    baseline = baseline[
        [
            "row_id", "test_year", "station", "group", "y", "openet",
            "Full", "SupportGain", "accept_SupportGain",
        ]
    ]
    predictions = []
    years = []
    with threadpool_limits(limits=1):
        for year in tier1_runner.TEST_YEARS:
            train = crop[crop.date.dt.year < year].copy()
            test = crop[crop.date.dt.year == year].copy().sort_values("row_id")
            if train.empty or test.empty:
                raise ValueError(f"Year {year} has an empty cropland train or test set")

            inner, inner_fits = tier3_runner.inner_predictions(
                crop, split_by_year[year]
            )
            weights = audit.station_weights(inner.station.to_numpy())
            features = tier3_runner.selector_features(inner, "base")
            gain_model = tier1_selective.gain_model()
            gain_model.fit(
                features,
                inner.gain.to_numpy(),
                sample_weight=weights / weights.mean(),
            )
            support_threshold = selective.weighted_quantile(
                inner.distance.to_numpy(), weights, 0.95
            )

            network, outer_fit = tier1_runner.fit_gridmet_ensemble(
                train[audit.FEATURES].to_numpy(),
                (train.y - train.openet).to_numpy(),
            )
            correction, spread, distance, _ = network.predict(
                test[audit.FEATURES].to_numpy()
            )
            outer = test.copy()
            outer["correction"] = correction
            outer["spread"] = spread
            outer["distance"] = distance
            gain_score = gain_model.predict(
                tier3_runner.selector_features(outer, "base")
            )
            accepted = (gain_score > 0) & (distance <= support_threshold)
            outer_output = outer[
                ["row_id", "station", "group", "date", "landcover", "y", "openet"]
            ].copy()
            outer_output["test_year"] = year
            outer_output["correction"] = correction
            outer_output["spread"] = spread
            outer_output["support_distance"] = distance
            outer_output["predicted_gain"] = gain_score
            outer_output["support_threshold"] = support_threshold
            outer_output["accept_CroplandOnlySupportGain"] = accepted
            outer_output["CroplandOnlyFull"] = outer.openet.to_numpy() + correction
            outer_output["CroplandOnlySupportGain"] = (
                outer.openet.to_numpy() + accepted * correction
            )
            predictions.append(outer_output)
            years.append({
                "test_year": year,
                "train_rows": int(len(train)),
                "train_stations": int(train.station.nunique()),
                "train_groups": int(train.group.nunique()),
                "test_rows": int(len(test)),
                "test_stations": int(test.station.nunique()),
                "test_groups": int(test.group.nunique()),
                "inner_rows": int(len(inner)),
                "inner_stations": int(inner.station.nunique()),
                "inner_groups": int(inner.group.nunique()),
                "support_threshold": float(support_threshold),
                "support_acceptance_rows": int(accepted.sum()),
                "inner_fits": inner_fits,
                "outer_fit": outer_fit,
            })

    crop_predictions = pd.concat(predictions, ignore_index=True).sort_values("row_id")
    baseline_crop = baseline[baseline.row_id.isin(crop_predictions.row_id)]
    baseline_crop = baseline_crop.sort_values("row_id").reset_index(drop=True)
    crop_predictions = crop_predictions.reset_index(drop=True)
    if not np.array_equal(
        baseline_crop.row_id.to_numpy(), crop_predictions.row_id.to_numpy()
    ):
        raise ValueError("The two training arms do not share identical test rows")
    for column in ["test_year", "station", "group", "y", "openet"]:
        left = baseline_crop[column].to_numpy()
        right = crop_predictions[column].to_numpy()
        if not np.array_equal(left, right):
            raise ValueError(f"Test row metadata differs for {column}")
    crop_predictions["AllStationFull"] = baseline_crop.Full.to_numpy()
    crop_predictions["AllStationSupportGain"] = baseline_crop.SupportGain.to_numpy()
    crop_predictions["accept_AllStationSupportGain"] = (
        baseline_crop.accept_SupportGain.to_numpy(dtype=bool)
    )

    predictions_path = OUT / "predictions_cropland_test.csv"
    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    crop_predictions.to_csv(predictions_path, index=False)
    input_paths = [
        PROTOCOL,
        COHORT,
        SPLITS,
        BASE_RECEIPT,
        BASE_PREDICTIONS,
        Path(__file__),
        ROOT / "scripts/ml_tier1_gridmet.py",
        ROOT / "scripts/ml_tier1_selective.py",
        ROOT / "scripts/ml_tier3_gridmet.py",
        ROOT / "scripts/ml_selective_residual.py",
        ROOT / "scripts/ml_transfer_audit.py",
    ]
    receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "run_script_sha256": sha256(Path(__file__)),
        "input_sha256": {
            str(path.relative_to(ROOT)): sha256(path) for path in input_paths
        },
        "predictions_sha256": sha256(predictions_path),
        "rows": int(len(crop_predictions)),
        "stations": int(crop_predictions.station.nunique()),
        "groups": int(crop_predictions.group.nunique()),
        "test_years": years,
        "fit_warnings": {
            "inner_members": sum(
                len(seed["warnings"])
                for year in years
                for fit in year["inner_fits"]
                for seed in fit["network_fit"]["seeds"]
            ),
            "outer_members": sum(
                len(seed["warnings"])
                for year in years
                for seed in year["outer_fit"]["seeds"]
            ),
        },
        "runtime_seconds": time.perf_counter() - started,
        "runtime_note": "One run. No timing interval was measured.",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
    }
    receipt_path = OUT / "run_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({
        "protocol_sha256": receipt["protocol_sha256"],
        "rows": receipt["rows"],
        "stations": receipt["stations"],
        "groups": receipt["groups"],
        "runtime_seconds": receipt["runtime_seconds"],
        "fit_warnings": receipt["fit_warnings"],
        "predictions_sha256": receipt["predictions_sha256"],
    }, indent=2))
    return receipt


if __name__ == "__main__":
    run()
