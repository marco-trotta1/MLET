"""Run the fixed clean-cohort selective fault experiment."""
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
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ml_selective_residual as selective
import ml_transfer_audit as audit

OUT = ROOT / "docs/results/ml_tier1_selective"
COHORT = ROOT / "docs/results/ml_tier1/cohort_clean.csv"
ALL_COHORT = audit.OUT / "cohort.csv"
SPLITS = audit.OUT / "splits.json"
FEATURES = audit.FEATURES
FAULT_SEED = 20260923
METHODS = [
    "OpenET", "Full", "Spread95", "Support95", "Gain", "SupportGain",
    "MonoGain", "AugmentedGain", "Uniform", "LocalShrinkage", "Clip",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gain_model(*, monotone: bool = False) -> HistGradientBoostingRegressor:
    arguments = {
        "max_iter": 80,
        "learning_rate": 0.05,
        "max_leaf_nodes": 7,
        "min_samples_leaf": 50,
        "l2_regularization": 10,
        "early_stopping": False,
        "random_state": audit.SEED,
    }
    if monotone:
        arguments["monotonic_cst"] = [0, 0, -1, -1, 0, 0]
    return HistGradientBoostingRegressor(**arguments)


def fault_inputs(frame: pd.DataFrame, inputs: np.ndarray,
                 training: pd.DataFrame, columns: list[str]) -> dict[str, np.ndarray]:
    variants = {"clean": inputs.copy()}
    wind = columns.index("ws")
    temp = columns.index("t_avg")
    vpd = columns.index("vpd")
    for factor in [0, 0.447, 1, 2.237, 3.6, 5, 10]:
        changed = inputs.copy()
        changed[:, wind] *= factor
        variants[f"wind_x{factor:g}"] = changed
    for offset in [5, 10, 20, 32]:
        changed = inputs.copy()
        changed[:, temp] += offset
        variants[f"temperature_plus{offset}"] = changed
    changed = inputs.copy()
    changed[:, temp] = changed[:, temp] * 9 / 5 + 32
    variants["temperature_fahrenheit_as_celsius"] = changed
    changed = inputs.copy()
    changed[:, vpd] *= 10
    variants["vpd_x10"] = changed

    changed = inputs.copy()
    changed[:, wind] = 0
    variants["wind_zero"] = changed
    changed = inputs.copy()
    changed[:, wind] = float(training.ws.median())
    variants["wind_dropout_median"] = changed

    ordered = frame[["station", "date"]].copy()
    ordered["position"] = np.arange(len(frame))
    changed = inputs.copy()
    for _, rows in ordered.groupby("station", sort=False):
        rows = rows.sort_values("date")
        values = inputs[rows.position.to_numpy(), wind].copy()
        dates = pd.to_datetime(rows.date).to_numpy()
        start = 0
        for index in range(1, len(rows) + 1):
            boundary = index == len(rows) or (dates[index] - dates[index - 1]).astype("timedelta64[D]").astype(int) != 1
            if boundary:
                for block in range(start, index, 7):
                    stop = min(block + 7, index)
                    values[block - start:stop - start] = values[block - start]
                start = index
        changed[rows.position.to_numpy(), wind] = values
    variants["wind_stuck_7_days"] = changed

    train_dates = pd.to_datetime(training.date)
    train_doy = train_dates.dt.dayofyear.to_numpy()
    means = pd.DataFrame({"doy": train_doy, "wind": training.ws.to_numpy()}).groupby("doy").wind.mean()
    global_mean = float(training.ws.mean())
    changed = inputs.copy()
    test_doy = pd.to_datetime(frame.date).dt.dayofyear
    changed[:, wind] = test_doy.map(means).fillna(global_mean).to_numpy()
    variants["wind_doy_climatology"] = changed
    return variants


def inner_training(train: pd.DataFrame, split: dict, columns: list[str]) -> tuple[
    pd.DataFrame, list[dict]
]:
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

        variants = fault_inputs(validation, inputs, fit, columns)
        fault_names = [name for name in variants if name != "clean"]
        rng = np.random.default_rng(FAULT_SEED + int(split["fold"]) * 10 + part_index)
        assignment = rng.integers(0, len(fault_names), len(validation))
        augmented_inputs = np.empty_like(inputs)
        augmented_correction = np.empty(len(validation))
        for index, name in enumerate(fault_names):
            selected = assignment == index
            if not selected.any():
                continue
            transformed = variants[name][selected]
            augmented_inputs[selected] = transformed
            augmented_correction[selected] = network.predict(transformed)[0]
        augmented_features = selective.selector_features(
            augmented_correction, spread, distance, augmented_inputs
        )
        augmented_gain = selective.improvement(
            validation.y.to_numpy(), validation.openet.to_numpy(), augmented_correction
        )
        augmented.append((augmented_features, augmented_gain, validation.station.to_numpy()))
    return pd.concat(frames).sort_values("row_id"), augmented


def fit_selectors(inner: pd.DataFrame, augmented: list[tuple], columns: list[str]) -> dict:
    weights = audit.station_weights(inner.station.to_numpy())
    spread_threshold = selective.weighted_quantile(inner.spread.to_numpy(), weights, 0.95)
    support_threshold = selective.weighted_quantile(inner.distance.to_numpy(), weights, 0.95)
    features = selective.selector_features(
        inner.correction.to_numpy(), inner.spread.to_numpy(),
        inner.distance.to_numpy(), inner[columns].to_numpy(),
    )
    weights = weights / weights.mean()
    gain = gain_model().fit(features, inner.gain.to_numpy(), sample_weight=weights)
    mono = gain_model(monotone=True).fit(features, inner.gain.to_numpy(), sample_weight=weights)
    aug_features = np.vstack([item[0] for item in augmented])
    aug_target = np.concatenate([item[1] for item in augmented])
    aug_stations = np.concatenate([item[2] for item in augmented])
    aug_weights = audit.station_weights(aug_stations)
    augmented_gain = gain_model().fit(
        aug_features, aug_target, sample_weight=aug_weights / aug_weights.mean()
    )

    residual = inner.y.to_numpy() - inner.openet.to_numpy()
    correction = inner.correction.to_numpy()
    moment_a = HistGradientBoostingRegressor(**gain_model().get_params())
    moment_b = HistGradientBoostingRegressor(**gain_model().get_params())
    moment_a.fit(features, residual * correction, sample_weight=weights)
    moment_b.fit(features, correction**2, sample_weight=weights)
    losses = {
        str(value): audit.macro_mae(
            inner.y.to_numpy(), inner.openet.to_numpy() + value * correction,
            inner.station.to_numpy(),
        )
        for value in [0, 0.25, 0.5, 0.75, 1]
    }
    return {
        "gain": gain, "mono": mono, "augmented": augmented_gain,
        "moment_a": moment_a, "moment_b": moment_b,
        "spread_threshold": spread_threshold,
        "support_threshold": support_threshold,
        "uniform": float(min(losses, key=losses.get)),
        "abs_correction_q95": float(np.quantile(np.abs(inner.correction), 0.95)),
        "spread_q95": float(np.quantile(inner.spread, 0.95)),
    }


def infer(frame: pd.DataFrame, network, selectors: dict, training: pd.DataFrame,
          columns: list[str]) -> dict[str, pd.DataFrame]:
    output = {}
    clean_inputs = frame[columns].to_numpy()
    for condition, inputs in fault_inputs(frame, clean_inputs, training, columns).items():
        mean, spread, distance, _ = network.predict(inputs)
        feature = selective.selector_features(mean, spread, distance, inputs)
        score = selectors["gain"].predict(feature)
        mono_score = selectors["mono"].predict(feature)
        augmented_score = selectors["augmented"].predict(feature)
        masks = {
            "Full": np.ones(len(frame), dtype=bool),
            "Spread95": spread <= selectors["spread_threshold"],
            "Support95": distance <= selectors["support_threshold"],
            "Gain": score > 0,
            "SupportGain": (distance <= selectors["support_threshold"]) & (score > 0),
            "MonoGain": mono_score > 0,
            "AugmentedGain": augmented_score > 0,
        }
        result = frame[["row_id", "station", "group", "date", "y", "openet"]].copy()
        result["OpenET"] = result.openet
        result["correction"] = mean
        result["abs_correction"] = np.abs(mean)
        result["spread"] = spread
        result["support_distance"] = distance
        result["predicted_gain"] = score
        result["predicted_monotone_gain"] = mono_score
        result["predicted_augmented_gain"] = augmented_score
        result["realized_gain"] = selective.improvement(
            result.y.to_numpy(), result.openet.to_numpy(), mean
        )
        result["train_abs_correction_q95"] = selectors["abs_correction_q95"]
        result["train_spread_q95"] = selectors["spread_q95"]
        for method, accepted in masks.items():
            result[method] = result.openet + accepted * mean
            result[f"accept_{method}"] = accepted
        result["Uniform"] = result.openet + selectors["uniform"] * mean
        predicted_a = selectors["moment_a"].predict(feature)
        predicted_b = selectors["moment_b"].predict(feature)
        local = np.zeros(len(frame))
        positive_b = predicted_b > 0
        local[positive_b] = np.clip(predicted_a[positive_b] / predicted_b[positive_b], 0, 1)
        result["LocalShrinkage"] = result.openet + local * mean
        result["accept_Uniform"] = selectors["uniform"] > 0
        result["accept_LocalShrinkage"] = local > 0
        result["lambda_Uniform"] = selectors["uniform"]
        result["lambda_LocalShrinkage"] = local
        lower = training[columns].quantile(0.01).to_numpy()
        upper = training[columns].quantile(0.99).to_numpy()
        weather = [columns.index(name) for name in ["eto", "t_avg", "vpd", "ws"]]
        clipped = inputs.copy()
        clipped[:, weather] = np.clip(clipped[:, weather], lower[weather], upper[weather])
        result["Clip"] = result.openet + network.predict(clipped)[0]
        result["fault"] = condition
        output[condition] = result
    return output


def evaluate_frame(frame: pd.DataFrame) -> dict:
    metrics = {}
    for name in METHODS:
        error = frame[name] - frame.y
        metrics[name] = {
            "station_macro_mae": audit.macro_mae(
                frame.y.to_numpy(), frame[name].to_numpy(), frame.station.to_numpy()
            ),
            "pooled_mae": float(np.abs(error).mean()),
            "rmse": float(np.sqrt(np.mean(error**2))),
            "vs_openet": audit.bootstrap(frame, "OpenET", name),
        }
        accept = f"accept_{name}"
        if accept in frame:
            metrics[name]["station_macro_acceptance"] = float(
                frame.groupby("station")[accept].mean().mean()
            )
        shrinkage = f"lambda_{name}"
        if shrinkage in frame:
            metrics[name]["mean_shrinkage"] = float(frame[shrinkage].mean())
    return metrics


def main() -> None:
    if (OUT / "results.json").exists():
        raise RuntimeError(f"Refusing to overwrite completed results in {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    clean = pd.read_csv(COHORT)
    original = pd.read_csv(ALL_COHORT)
    split_records = json.loads(SPLITS.read_text())
    collected: dict[str, list[pd.DataFrame]] = {}
    fold_records = []
    started = time.perf_counter()
    columns = FEATURES

    for split in [item for item in split_records if item["regime"] == "proximity"]:
        train = clean[clean.row_id.isin(split["train_row_ids"])]
        test = clean[clean.row_id.isin(split["test_row_ids"])]
        inner, augmented = inner_training(train, split, columns)
        selectors = fit_selectors(inner, augmented, columns)
        network, timing = selective.fit_ensemble(
            train[columns].to_numpy(), (train.y - train.openet).to_numpy()
        )
        for condition, result in infer(test, network, selectors, train, columns).items():
            collected.setdefault(condition, []).append(result)

        natural = original[
            original.row_id.isin(split["test_row_ids"])
            & (original.station == "manilacotton")
        ]
        if not natural.empty:
            for condition, result in infer(natural, network, selectors, train, columns).items():
                result["fault"] = "manilacotton_" + condition
                collected.setdefault("manilacotton_" + condition, []).append(result)
        fold_records.append({
            "fold": split["fold"], "train_rows": len(train), "test_rows": len(test),
            "inner_rows": len(inner), "augmented_rows": len(augmented) * len(inner) // 3,
            "fit_seconds": timing["fit_seconds"], "uniform_multiplier": selectors["uniform"],
        })
        print(f"proximity fold {split['fold']} complete", flush=True)

    results = {}
    for condition, frames in collected.items():
        data = pd.concat(frames, ignore_index=True).sort_values("row_id")
        data.to_csv(OUT / f"predictions_{condition}.csv", index=False)
        results[condition] = {
            "rows": len(data), "stations": int(data.station.nunique()),
            "groups": int(data.group.nunique()),
            "models": evaluate_frame(data),
        }
    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    receipt = {
        "seconds": time.perf_counter() - started,
        "code_sha256": sha(Path(__file__)),
        "protocol_sha256": sha(ROOT / "docs/evaluation/ML_TIER1_SELECTIVE_PROTOCOL.md"),
        "clean_cohort_sha256": sha(COHORT),
        "original_cohort_sha256": sha(ALL_COHORT),
        "split_sha256": sha(SPLITS),
        "versions": {"numpy": np.__version__, "pandas": pd.__version__,
                     "scikit_learn": sklearn.__version__},
        "platform": platform.platform(), "fault_seed": FAULT_SEED,
        "neural_seeds": selective.SEEDS,
        "primary_comparisons": [
            "Gain versus SupportGain across clean, wind, temperature, and VPD probes",
            "MonoGain versus SupportGain across the same probes",
            "AugmentedGain versus SupportGain across the same probes",
            "LocalShrinkage versus Uniform on clean and each fault",
        ],
        "folds": fold_records,
    }
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2))
    print("Tier 1 selective experiment complete.", flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        main()
