"""Run the fixed all-station, rolling-origin Tier 1 experiment."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.neighbors import NearestNeighbors
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ml_selective_residual as selective
import ml_tier1_selective as tier1
import ml_transfer_audit as audit

OUT = ROOT / "docs/results/ml_tier1_gridmet_10member"
COHORT = ROOT / "docs/results/ml_tier1_gridmet/cohort.csv"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_GRIDMET_10MEMBER_PROTOCOL.md"
SPLIT_SEED = 20260924
TEST_YEARS = list(range(2012, 2021))
NEURAL_SEEDS = list(range(audit.SEED, audit.SEED + 10))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit_gridmet_ensemble(inputs: np.ndarray, residual: np.ndarray) -> tuple[selective.Ensemble, dict]:
    started = time.perf_counter()
    scaler = StandardScaler().fit(inputs)
    scaled = scaler.transform(inputs)
    center = float(residual.mean())
    scale = max(float(residual.std()), 1e-12)
    models = []
    records = []
    for seed in NEURAL_SEEDS:
        model = MLPRegressor(
            hidden_layer_sizes=(32, 32),
            activation="relu",
            solver="adam",
            alpha=0.001,
            batch_size=256,
            learning_rate_init=0.001,
            max_iter=120,
            early_stopping=False,
            n_iter_no_change=121,
            tol=0,
            random_state=seed,
        )
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter("always", ConvergenceWarning)
            model.fit(scaled, (residual - center) / scale)
        models.append(model)
        records.append(
            {
                "seed": seed,
                "iterations": model.n_iter_,
                "loss": float(model.loss_),
                "warnings": [str(warning.message) for warning in observed],
            }
        )
    neighbors = NearestNeighbors(n_neighbors=5, n_jobs=1).fit(scaled)
    ensemble = selective.Ensemble(scaler, models, center, scale, neighbors)
    return ensemble, {
        "fit_seconds": time.perf_counter() - started,
        "train_rows": len(inputs),
        "seeds": records,
    }


def grouped_bootstrap(frame: pd.DataFrame, method: str) -> dict:
    station = frame.assign(
        delta=np.abs(frame.y - frame.openet) - np.abs(frame.y - frame[method])
    ).groupby(["group", "station"], sort=True).delta.mean().reset_index()
    groups = station.groupby("group").delta.agg(["sum", "count"])
    point = float(station.delta.mean())
    rng = np.random.default_rng(SPLIT_SEED)
    indices = rng.integers(0, len(groups), size=(2000, len(groups)))
    sums = groups["sum"].to_numpy()[indices].sum(axis=1)
    counts = groups["count"].to_numpy()[indices].sum(axis=1)
    low, high = np.quantile(sums / counts, [0.025, 0.975])
    return {
        "delta_macro_mae": point,
        "ci95": [float(low), float(high)],
        "stations": int(len(station)),
        "groups": int(len(groups)),
        "rows": int(len(frame)),
    }


def evaluate(frame: pd.DataFrame) -> dict:
    summary = {}
    for method in tier1.METHODS:
        error = frame[method].to_numpy() - frame.y.to_numpy()
        summary[method] = {
            "station_macro_mae": audit.macro_mae(
                frame.y.to_numpy(), frame[method].to_numpy(), frame.station.to_numpy()
            ),
            "pooled_mae": float(np.abs(error).mean()),
            "rmse": float(np.sqrt(np.mean(error ** 2))),
            "vs_openet": grouped_bootstrap(frame, method),
        }
        accepted = f"accept_{method}"
        if accepted in frame:
            summary[method]["station_macro_acceptance"] = float(
                frame.groupby("station")[accepted].mean().mean()
            )
        shrinkage = f"lambda_{method}"
        if shrinkage in frame:
            summary[method]["mean_shrinkage"] = float(frame[shrinkage].mean())
    return summary


def inner_split(train: pd.DataFrame, year: int) -> dict:
    groups = sorted(train.group.unique())
    if len(groups) < 3:
        raise ValueError(f"rolling origin {year} has fewer than three training groups")
    folds = audit.field_withheld_folds(groups, 3, SPLIT_SEED + year)
    partitions = []
    for fit_groups, validation_groups in folds:
        fit = train.loc[train.group.isin(fit_groups), "row_id"].astype(int).tolist()
        validation = train.loc[train.group.isin(validation_groups), "row_id"].astype(int).tolist()
        partitions.append({"train_row_ids": fit, "validation_row_ids": validation})
    return {"fold": year, "inner_partitions": partitions}


def inner_training(
    train: pd.DataFrame, split: dict, columns: list[str]
) -> tuple[pd.DataFrame, list[tuple], list[dict]]:
    frames = []
    augmented = []
    fit_records = []
    for part_index, part in enumerate(split["inner_partitions"]):
        fit = train[train.row_id.isin(part["train_row_ids"])]
        validation = train[train.row_id.isin(part["validation_row_ids"])]
        if fit.empty or validation.empty:
            continue
        network, timing = fit_gridmet_ensemble(
            fit[columns].to_numpy(), (fit.y - fit.openet).to_numpy()
        )
        fit_records.append(
            {
                "part": part_index,
                "train_rows": len(fit),
                "validation_rows": len(validation),
                "network_fit": timing,
            }
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
        frames.append(inner)

        variants = tier1.fault_inputs(validation, inputs, fit, columns)
        fault_names = [name for name in variants if name != "clean"]
        rng = np.random.default_rng(tier1.FAULT_SEED + int(split["fold"]) * 10 + part_index)
        assignment = rng.integers(0, len(fault_names), len(validation))
        augmented_inputs = np.empty_like(inputs)
        augmented_correction = np.empty(len(validation))
        augmented_spread = np.empty(len(validation))
        augmented_distance = np.empty(len(validation))
        for index, name in enumerate(fault_names):
            selected = assignment == index
            if selected.any():
                transformed = variants[name][selected]
                augmented_inputs[selected] = transformed
                (
                    augmented_correction[selected],
                    augmented_spread[selected],
                    augmented_distance[selected],
                    _,
                ) = network.predict(transformed)
        augmented_features = selective.selector_features(
            augmented_correction, augmented_spread, augmented_distance, augmented_inputs
        )
        augmented_gain = selective.improvement(
            validation.y.to_numpy(), validation.openet.to_numpy(), augmented_correction
        )
        augmented.append(
            (augmented_features, augmented_gain, validation.station.to_numpy())
        )
    if not frames:
        raise ValueError(f"rolling origin {split['fold']} has no valid inner predictions")
    return pd.concat(frames).sort_values("row_id"), augmented, fit_records


def run() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise RuntimeError(f"Refusing to overwrite existing results in {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    cohort = pd.read_csv(COHORT, parse_dates=["date"])
    columns = audit.FEATURES
    predictions: dict[str, list[pd.DataFrame]] = {}
    year_records = []
    split_records = []
    started = time.perf_counter()

    for year in TEST_YEARS:
        train = cohort.loc[cohort.date.dt.year < year].copy()
        test = cohort.loc[cohort.date.dt.year == year].copy()
        if train.empty or test.empty:
            raise ValueError(f"rolling origin {year} has no training or test rows")
        split = inner_split(train, year)
        split_records.append({"test_year": year, **split})
        inner, augmented, inner_fits = inner_training(train, split, columns)
        selector_started = time.perf_counter()
        selectors = tier1.fit_selectors(inner, augmented, columns)
        selector_seconds = time.perf_counter() - selector_started
        network, timing = fit_gridmet_ensemble(
            train[columns].to_numpy(), (train.y - train.openet).to_numpy()
        )
        for condition, frame in tier1.infer(test, network, selectors, train, columns).items():
            frame["test_year"] = year
            predictions.setdefault(condition, []).append(frame)
        year_records.append(
            {
                "test_year": year,
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "train_stations": int(train.station.nunique()),
                "test_stations": int(test.station.nunique()),
                "train_groups": int(train.group.nunique()),
                "inner_rows": int(len(inner)),
                "inner_fits": inner_fits,
                "selector_fit_seconds": selector_seconds,
                "outer_network_fit": timing,
                "uniform_multiplier": selectors["uniform"],
                "inner_seed": SPLIT_SEED + year,
            }
        )
        print(f"rolling origin {year} complete", flush=True)

    results = {}
    for condition, frames in predictions.items():
        data = pd.concat(frames, ignore_index=True).sort_values(["test_year", "row_id"])
        data.to_csv(OUT / f"predictions_{condition}.csv", index=False)
        results[condition] = {
            "rows": int(len(data)),
            "stations": int(data.station.nunique()),
            "groups": int(data.group.nunique()),
            "test_years": {
                str(year): evaluate(part)
                for year, part in data.groupby("test_year", sort=True)
            },
            "pooled": evaluate(data),
        }
    (OUT / "results.json").write_text(json.dumps(results, indent=2) + chr(10))
    splits_path = OUT / "splits.json"
    splits_path.write_text(json.dumps(split_records) + chr(10))
    receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "script_sha256": sha256(Path(__file__)),
        "cohort_sha256": sha256(COHORT),
        "splits_sha256": sha256(splits_path),
        "split_seed": SPLIT_SEED,
        "test_years": TEST_YEARS,
        "neural_seeds": NEURAL_SEEDS,
        "fault_seed": tier1.FAULT_SEED,
        "versions": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "platform": platform.platform(),
        "seconds": time.perf_counter() - started,
        "years": year_records,
    }
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + chr(10))
    print("Tier 1 all-station temporal experiment complete.", flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        run()
