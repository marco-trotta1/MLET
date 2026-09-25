"""Fit tuned and standard deferral baselines on frozen gridMET predictions."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_ml_tier1_gridmet as tier1_analysis
import ml_selective_residual as selective
import ml_tier1_gridmet as tier1_runner
import ml_tier1_selective as tier1_selective
import ml_transfer_audit as audit

BASE = ROOT / "docs/results/ml_tier1_gridmet_10member"
OUT = ROOT / "docs/results/ml_tier3_gridmet"
COHORT = ROOT / "docs/results/ml_tier1_gridmet/cohort.csv"
BASE_RECEIPT = BASE / "receipt.json"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER3_GRIDMET_PROTOCOL.md"
FEATURES = audit.FEATURES
CONDITIONS = tier1_analysis.CONDITIONS
FEATURE_SETS = ["base", "raw_weather", "day_of_year", "raw_weather_day_of_year"]
ITERATIONS = [40, 80, 120]
LEAF_NODES = [3, 7, 15]
LEARNING_RATES = [0.03, 0.05, 0.10]
SEED = 20260924
TEST_YEARS = tier1_runner.TEST_YEARS


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def selector_features(frame: pd.DataFrame, feature_set: str) -> np.ndarray:
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"Unknown selector feature set: {feature_set}")
    inputs = frame[FEATURES].to_numpy()
    distance_name = "support_distance" if "support_distance" in frame else "distance"
    features = [
        selective.selector_features(
            frame.correction.to_numpy(),
            frame.spread.to_numpy(),
            frame[distance_name].to_numpy(),
            inputs,
        )
    ]
    if feature_set in ["raw_weather", "raw_weather_day_of_year"]:
        features.append(frame[["t_avg", "vpd", "ws"]].to_numpy())
    if feature_set in ["day_of_year", "raw_weather_day_of_year"]:
        features.append(frame[["doy_sin", "doy_cos"]].to_numpy())
    return np.column_stack(features)


def gain_regressor(*, iterations: int, leaves: int, learning_rate: float) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=iterations,
        learning_rate=learning_rate,
        max_leaf_nodes=leaves,
        min_samples_leaf=50,
        l2_regularization=10,
        early_stopping=False,
        random_state=audit.SEED,
    )


def normalized_station_weights(stations: np.ndarray) -> np.ndarray:
    weights = audit.station_weights(stations)
    return weights / weights.mean()


def tune_gain(inner: pd.DataFrame) -> tuple[HistGradientBoostingRegressor, dict]:
    folds = sorted(inner.inner_fold.unique())
    candidates = []
    feature_cache = {
        name: selector_features(inner, name) for name in FEATURE_SETS
    }
    for feature_order, feature_set in enumerate(FEATURE_SETS):
        features = feature_cache[feature_set]
        for iterations, leaves, learning_rate in itertools.product(
            ITERATIONS, LEAF_NODES, LEARNING_RATES
        ):
            fold_mae = []
            for held_fold in folds:
                fit_mask = inner.inner_fold.to_numpy() != held_fold
                validation_mask = ~fit_mask
                fit = inner.loc[fit_mask]
                validation = inner.loc[validation_mask]
                model = gain_regressor(
                    iterations=iterations,
                    leaves=leaves,
                    learning_rate=learning_rate,
                )
                model.fit(
                    features[fit_mask],
                    fit.gain.to_numpy(),
                    sample_weight=normalized_station_weights(fit.station.to_numpy()),
                )
                accepted = model.predict(features[validation_mask]) > 0
                prediction = validation.openet.to_numpy() + (
                    accepted * validation.correction.to_numpy()
                )
                fold_mae.append(
                    audit.macro_mae(
                        validation.y.to_numpy(),
                        prediction,
                        validation.station.to_numpy(),
                    )
                )
            candidates.append(
                {
                    "feature_set": feature_set,
                    "feature_order": feature_order,
                    "iterations": iterations,
                    "leaves": leaves,
                    "learning_rate": learning_rate,
                    "fold_station_macro_mae": fold_mae,
                    "mean_station_macro_mae": float(np.mean(fold_mae)),
                }
            )
    best = min(
        candidates,
        key=lambda item: (
            item["mean_station_macro_mae"],
            item["iterations"],
            item["leaves"],
            item["learning_rate"],
            item["feature_order"],
        ),
    )
    features = feature_cache[best["feature_set"]]
    model = gain_regressor(
        iterations=best["iterations"],
        leaves=best["leaves"],
        learning_rate=best["learning_rate"],
    )
    model.fit(
        features,
        inner.gain.to_numpy(),
        sample_weight=normalized_station_weights(inner.station.to_numpy()),
    )
    return model, {"best": best, "candidates": candidates}


def fit_sign_classifier(inner: pd.DataFrame) -> tuple[StandardScaler, LogisticRegression, dict]:
    features = selector_features(inner, "raw_weather_day_of_year")
    labels = (inner.gain.to_numpy() > 0).astype(int)
    if np.unique(labels).size != 2:
        raise ValueError("The sign classifier requires positive and nonpositive gains")
    scaler = StandardScaler().fit(features)
    model = LogisticRegression(
        C=1.0,
        class_weight="balanced",
        max_iter=1000,
        random_state=audit.SEED,
    )
    model.fit(
        scaler.transform(features),
        labels,
        sample_weight=normalized_station_weights(inner.station.to_numpy()),
    )
    return scaler, model, {
        "rows": int(len(inner)),
        "positive_gain_rows": int(labels.sum()),
        "positive_gain_rate": float(labels.mean()),
        "feature_set": "raw_weather_day_of_year",
    }


def conformal_offset(group_scores: np.ndarray, alpha: float = 0.05) -> float:
    scores = np.asarray(group_scores, dtype=float)
    if scores.ndim != 1 or len(scores) == 0 or not np.isfinite(scores).all():
        raise ValueError("Conformal calibration requires finite group scores")
    if not 0 < alpha < 1:
        raise ValueError("Conformal alpha must be between zero and one")
    rank = math.ceil((len(scores) + 1) * (1 - alpha))
    if rank > len(scores):
        return float("inf")
    return float(np.sort(scores)[rank - 1])


def split_csr_groups(groups: list[str], seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(groups) < 3:
        raise ValueError("Conformal fitting requires at least three spatial groups")
    shuffled = np.random.default_rng(seed).permutation(np.array(sorted(groups)))
    fit_groups, calibration_groups, threshold_groups = np.array_split(shuffled, 3)
    return fit_groups, calibration_groups, threshold_groups


def quantile_regressor(alpha: float) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="quantile",
        quantile=alpha,
        max_iter=80,
        learning_rate=0.05,
        max_leaf_nodes=7,
        min_samples_leaf=50,
        l2_regularization=10,
        early_stopping=False,
        random_state=audit.SEED,
    )


def ordered_interval(
    lower: np.ndarray, upper: np.ndarray, offset: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lower_bound = np.minimum(lower, upper) - offset
    upper_bound = np.maximum(lower, upper) + offset
    width = np.maximum(upper_bound - lower_bound, 0)
    return lower_bound, upper_bound, width


def select_interval_threshold(frame: pd.DataFrame, width: np.ndarray) -> tuple[float, float, float]:
    if len(frame) != len(width) or len(width) == 0 or np.isnan(width).any():
        raise ValueError("Threshold selection requires one nonmissing width per row")
    finite_widths = width[np.isfinite(width)]
    if len(finite_widths):
        candidates = np.concatenate(
            [
                [np.nextafter(float(finite_widths.min()), -np.inf)],
                np.unique(finite_widths),
            ]
        )
    else:
        candidates = np.array([np.nextafter(float("inf"), -np.inf)])
    best_threshold = float(candidates[0])
    best_risk = float("inf")
    best_coverage = -1.0
    for threshold in candidates:
        accepted = width <= threshold
        prediction = frame.openet.to_numpy() + (
            accepted * frame.correction.to_numpy()
        )
        risk = audit.macro_mae(
            frame.y.to_numpy(), prediction, frame.station.to_numpy()
        )
        coverage = float(accepted.mean())
        # Treat MAE gaps under 1e-12 mm/day as floating-point ties before preferring coverage.
        if risk < best_risk - 1e-12:
            best_threshold = float(threshold)
            best_risk = risk
            best_coverage = coverage
        elif np.isclose(risk, best_risk, rtol=0, atol=1e-12) and coverage > best_coverage:
            best_threshold = float(threshold)
            best_coverage = coverage
    return best_threshold, best_risk, best_coverage


def fit_conformal_selector(inner: pd.DataFrame, seed: int) -> tuple[dict, dict]:
    fit_groups, calibration_groups, threshold_groups = split_csr_groups(
        sorted(inner.group.unique()), seed
    )
    fit = inner[inner.group.isin(fit_groups)]
    calibration = inner[inner.group.isin(calibration_groups)]
    threshold_rows = inner[inner.group.isin(threshold_groups)]
    features = selector_features(inner, "raw_weather_day_of_year")
    positions = {int(row_id): index for index, row_id in enumerate(inner.row_id)}
    fit_index = np.array([positions[int(row_id)] for row_id in fit.row_id])
    calibration_index = np.array(
        [positions[int(row_id)] for row_id in calibration.row_id]
    )
    threshold_index = np.array(
        [positions[int(row_id)] for row_id in threshold_rows.row_id]
    )
    residual_error = inner.y.to_numpy() - inner.openet.to_numpy() - inner.correction.to_numpy()
    weights = normalized_station_weights(fit.station.to_numpy())
    lower_model = quantile_regressor(0.025).fit(
        features[fit_index], residual_error[fit_index], sample_weight=weights
    )
    upper_model = quantile_regressor(0.975).fit(
        features[fit_index], residual_error[fit_index], sample_weight=weights
    )
    lower_calibration = lower_model.predict(features[calibration_index])
    upper_calibration = upper_model.predict(features[calibration_index])
    ordered_lower = np.minimum(lower_calibration, upper_calibration)
    ordered_upper = np.maximum(lower_calibration, upper_calibration)
    calibration_error = residual_error[calibration_index]
    conformity = np.maximum(
        calibration_error - ordered_upper,
        ordered_lower - calibration_error,
    )
    group_scores = pd.DataFrame(
        {"group": calibration.group.to_numpy(), "score": conformity}
    ).groupby("group", sort=True).score.max().to_numpy()
    offset = conformal_offset(group_scores)
    low, high, calibration_width = ordered_interval(
        ordered_lower, ordered_upper, offset
    )
    lower_threshold = lower_model.predict(features[threshold_index])
    upper_threshold = upper_model.predict(features[threshold_index])
    _, _, threshold_width = ordered_interval(
        lower_threshold, upper_threshold, offset
    )
    threshold, threshold_risk, threshold_coverage = select_interval_threshold(
        threshold_rows, threshold_width
    )
    selectors = {
        "lower_model": lower_model,
        "upper_model": upper_model,
        "offset": offset,
        "threshold": threshold,
    }
    record = {
        "alpha": 0.05,
        "fit_groups": sorted(map(str, fit_groups)),
        "calibration_groups": sorted(map(str, calibration_groups)),
        "threshold_groups": sorted(map(str, threshold_groups)),
        "fit_rows": int(len(fit)),
        "calibration_rows": int(len(calibration)),
        "calibration_group_count": int(len(group_scores)),
        "calibration_group_score_max": float(np.max(group_scores)),
        "offset": offset,
        "threshold_rows": int(len(threshold_rows)),
        "threshold": threshold,
        "threshold_station_macro_mae": threshold_risk,
        "threshold_acceptance": threshold_coverage,
        "mean_calibration_width": (
            float(calibration_width.mean())
            if np.isfinite(calibration_width).all()
            else None
        ),
    }
    return selectors, record


def inner_predictions(
    cohort: pd.DataFrame, split: dict
) -> tuple[pd.DataFrame, list[dict]]:
    year = int(split["test_year"])
    training = cohort[cohort.date.dt.year < year]
    frames = []
    records = []
    for part_index, part in enumerate(split["inner_partitions"]):
        fit = training[training.row_id.isin(part["train_row_ids"])]
        validation = training[training.row_id.isin(part["validation_row_ids"])]
        network, timing = tier1_runner.fit_gridmet_ensemble(
            fit[FEATURES].to_numpy(),
            (fit.y - fit.openet).to_numpy(),
        )
        mean, spread, distance, _ = network.predict(validation[FEATURES].to_numpy())
        inner = validation.copy()
        inner["correction"] = mean
        inner["spread"] = spread
        inner["distance"] = distance
        inner["gain"] = selective.improvement(
            validation.y.to_numpy(), validation.openet.to_numpy(), mean
        )
        inner["inner_fold"] = part_index
        frames.append(inner)
        records.append(
            {
                "fold": part_index,
                "fit_rows": int(len(fit)),
                "validation_rows": int(len(validation)),
                "network_fit": timing,
            }
        )
    return pd.concat(frames, ignore_index=True).sort_values("row_id"), records


def replace_features(frame: pd.DataFrame, inputs: np.ndarray) -> pd.DataFrame:
    output = frame.copy()
    for index, name in enumerate(FEATURES):
        output[name] = inputs[:, index]
    return output


def load_test_condition(
    cohort: pd.DataFrame, training: pd.DataFrame, year: int, condition: str
) -> pd.DataFrame:
    prediction_path = BASE / f"predictions_{condition}.csv"
    predictions = pd.read_csv(prediction_path, parse_dates=["date"])
    predictions = predictions[predictions.test_year == year].sort_values("row_id")
    feature_columns = [name for name in FEATURES if name != "openet"]
    frame = predictions.merge(
        cohort[["row_id", *feature_columns]],
        on="row_id",
        validate="one_to_one",
    )
    clean_inputs = frame[FEATURES].to_numpy()
    variants = tier1_selective.fault_inputs(
        frame, clean_inputs, training, FEATURES
    )
    if condition not in variants:
        raise ValueError(f"Unknown Tier 1 condition: {condition}")
    return replace_features(frame, variants[condition])


def predict_new_methods(
    frame: pd.DataFrame,
    tuned_gain: HistGradientBoostingRegressor,
    tuned_config: dict,
    sign_scaler: StandardScaler,
    sign_model: LogisticRegression,
    conformal: dict,
) -> pd.DataFrame:
    output = frame.copy()
    tuned_score = tuned_gain.predict(
        selector_features(frame, tuned_config["feature_set"])
    )
    output["TunedGain"] = frame.openet + (tuned_score > 0) * frame.correction
    output["accept_TunedGain"] = tuned_score > 0
    sign_features = selector_features(frame, "raw_weather_day_of_year")
    sign_probability = sign_model.predict_proba(
        sign_scaler.transform(sign_features)
    )[:, 1]
    output["LogisticSign"] = (
        frame.openet + (sign_probability >= 0.5) * frame.correction
    )
    output["accept_LogisticSign"] = sign_probability >= 0.5
    conformal_features = selector_features(frame, "raw_weather_day_of_year")
    lower = conformal["lower_model"].predict(conformal_features)
    upper = conformal["upper_model"].predict(conformal_features)
    _, _, width = ordered_interval(lower, upper, conformal["offset"])
    accepted = width <= conformal["threshold"]
    output["ConformalCSR"] = frame.openet + accepted * frame.correction
    output["accept_ConformalCSR"] = accepted
    output["conformal_width"] = width
    output["logistic_sign_probability"] = sign_probability
    output["tuned_predicted_gain"] = tuned_score
    return output


def evaluate_method(frame: pd.DataFrame, method: str) -> dict:
    error = frame[method].to_numpy() - frame.y.to_numpy()
    acceptance = f"accept_{method}"
    return {
        "station_macro_mae": audit.macro_mae(
            frame.y.to_numpy(), frame[method].to_numpy(), frame.station.to_numpy()
        ),
        "pooled_mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "station_macro_acceptance": (
            float(frame.groupby("station")[acceptance].mean().mean())
            if acceptance in frame
            else None
        ),
        "vs_openet": tier1_runner.grouped_bootstrap(frame, method),
    }


def run() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise RuntimeError(f"Refusing to overwrite existing results in {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    cohort = pd.read_csv(COHORT, parse_dates=["date"])
    splits = json.loads((BASE / "splits.json").read_text())
    splits_by_year = {int(record["test_year"]): record for record in splits}
    predictions: dict[str, list[pd.DataFrame]] = {condition: [] for condition in CONDITIONS}
    records = []
    started = time.perf_counter()

    for year in TEST_YEARS:
        training = cohort[cohort.date.dt.year < year]
        split = splits_by_year[year]
        inner, inner_fits = inner_predictions(cohort, split)
        tuning_started = time.perf_counter()
        tuned_gain, tuning_record = tune_gain(inner)
        tuning_record["seconds"] = time.perf_counter() - tuning_started
        sign_started = time.perf_counter()
        sign_scaler, sign_model, sign_record = fit_sign_classifier(inner)
        sign_record["seconds"] = time.perf_counter() - sign_started
        conformal_started = time.perf_counter()
        conformal, conformal_record = fit_conformal_selector(
            inner, SEED + year
        )
        conformal_record["seconds"] = time.perf_counter() - conformal_started
        selected_config = tuning_record["best"]
        for condition in CONDITIONS:
            frame = load_test_condition(cohort, training, year, condition)
            frame = predict_new_methods(
                frame,
                tuned_gain,
                selected_config,
                sign_scaler,
                sign_model,
                conformal,
            )
            predictions[condition].append(frame)
        records.append(
            {
                "test_year": year,
                "train_rows": int(len(training)),
                "inner_rows": int(len(inner)),
                "inner_fits": inner_fits,
                "tuning": tuning_record,
                "sign_classifier": sign_record,
                "conformal": conformal_record,
            }
        )
        print(f"Tier 3 selectors complete for {year}", flush=True)

    results = {}
    for condition, frames in predictions.items():
        data = pd.concat(frames, ignore_index=True).sort_values(["test_year", "row_id"])
        data.to_csv(OUT / f"predictions_{condition}.csv", index=False)
        methods = [
            "OpenET",
            "Gain",
            "SupportGain",
            "MonoGain",
            "AugmentedGain",
            "Uniform",
            "LocalShrinkage",
            "TunedGain",
            "LogisticSign",
            "ConformalCSR",
        ]
        results[condition] = {
            "rows": int(len(data)),
            "stations": int(data.station.nunique()),
            "groups": int(data.group.nunique()),
            "test_years": {
                str(year): {
                    method: evaluate_method(part, method)
                    for method in methods
                }
                for year, part in data.groupby("test_year", sort=True)
            },
            "pooled": {
                method: evaluate_method(data, method) for method in methods
            },
        }
    (OUT / "results.json").write_text(json.dumps(results, indent=2) + chr(10))
    (OUT / "selector_receipt.json").write_text(json.dumps(records, indent=2) + chr(10))
    receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "script_sha256": sha256(Path(__file__)),
        "cohort_sha256": sha256(COHORT),
        "base_run_receipt_sha256": sha256(BASE_RECEIPT),
        "base_outer_predictions": {
            condition: sha256(BASE / f"predictions_{condition}.csv")
            for condition in CONDITIONS
        },
        "base_splits_sha256": sha256(BASE / "splits.json"),
        "seed": SEED,
        "test_years": TEST_YEARS,
        "neural_seeds": tier1_runner.NEURAL_SEEDS,
        "versions": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "platform": platform.platform(),
        "seconds": time.perf_counter() - started,
    }
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + chr(10))
    print("Tier 3 gridMET selector run complete.", flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        run()
