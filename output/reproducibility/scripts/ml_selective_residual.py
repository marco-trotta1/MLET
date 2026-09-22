"""Evaluate selective neural corrections with spatially cross-fitted selectors."""
from __future__ import annotations

import json
import platform
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import roc_auc_score
from sklearn.neighbors import NearestNeighbors
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

import ml_transfer_audit as audit

OUT = audit.ROOT / "docs/results/ml_selective"
SEEDS = [audit.SEED, audit.SEED + 1, audit.SEED + 2]
METHODS = ["OpenET", "Full", "Spread95", "Support95", "Gain", "SupportGain", "Uniform", "Clip"]


def improvement(y: np.ndarray, baseline: np.ndarray, correction: np.ndarray) -> np.ndarray:
    """Return the absolute-error reduction from applying a correction."""
    return np.abs(y - baseline) - np.abs(y - baseline - correction)


def weighted_quantile(values: np.ndarray, weights: np.ndarray, fraction: float) -> float:
    """Return a weighted empirical quantile with stable tie ordering."""
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    index = np.searchsorted(cumulative, fraction * cumulative[-1], side="left")
    return float(values[order[min(index, len(order) - 1)]])


def selector_features(mean: np.ndarray, spread: np.ndarray, distance: np.ndarray,
                      inputs: np.ndarray) -> np.ndarray:
    return np.column_stack([mean, np.abs(mean), spread, np.log1p(distance), inputs[:, :2]])


@dataclass
class Ensemble:
    scaler: StandardScaler
    models: list[MLPRegressor]
    target_mean: float
    target_scale: float
    neighbors: NearestNeighbors

    def predict(self, inputs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        scaled = self.scaler.transform(inputs)
        seeds = np.column_stack([m.predict(scaled) * self.target_scale + self.target_mean for m in self.models])
        distance = self.neighbors.kneighbors(scaled, return_distance=True)[0].mean(axis=1)
        return seeds.mean(axis=1), seeds.std(axis=1, ddof=1), distance, seeds


def fit_ensemble(inputs: np.ndarray, residual: np.ndarray) -> tuple[Ensemble, dict]:
    start = time.perf_counter()
    scaler = StandardScaler().fit(inputs)
    scaled = scaler.transform(inputs)
    center = float(residual.mean())
    scale = max(float(residual.std()), 1e-12)
    models = []
    records = []
    for seed in SEEDS:
        model = MLPRegressor(hidden_layer_sizes=(32, 32), activation="relu", solver="adam",
                             alpha=.001, batch_size=256, learning_rate_init=.001, max_iter=120,
                             early_stopping=False, n_iter_no_change=121, tol=0, random_state=seed)
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter("always", ConvergenceWarning)
            model.fit(scaled, (residual - center) / scale)
        models.append(model)
        records.append({"seed": seed, "iterations": model.n_iter_, "loss": float(model.loss_),
                        "warnings": [str(w.message) for w in observed]})
    neighbors = NearestNeighbors(n_neighbors=5, n_jobs=1).fit(scaled)
    return Ensemble(scaler, models, center, scale, neighbors), {
        "fit_seconds": time.perf_counter() - start, "train_rows": len(inputs), "seeds": records}


def evaluate_methods(frame: pd.DataFrame) -> dict:
    results = {}
    for name in METHODS:
        error = frame[name] - frame.y
        results[name] = {"macro_mae": audit.macro_mae(frame.y, frame[name], frame.station.to_numpy()),
                         "pooled_mae": float(np.abs(error).mean()),
                         "rmse": float(np.sqrt(np.mean(error ** 2))),
                         "vs_openet": audit.bootstrap(frame, "OpenET", name)}
        accept = "accept_" + name
        if accept in frame:
            results[name]["acceptance"] = float(frame[accept].mean())
            results[name]["station_acceptance"] = float(frame.groupby("station")[accept].mean().mean())
    return results


def curve_records(frame: pd.DataFrame, inner: pd.DataFrame) -> list[dict]:
    weights = audit.station_weights(inner.station.to_numpy())
    curves = []
    for score, direction in [("spread", 1), ("distance", 1), ("predicted_gain", -1)]:
        for q in np.linspace(0, 1, 11):
            if q <= 0:
                accepted = np.zeros(len(frame), dtype=bool)
            elif q >= 1:
                accepted = np.ones(len(frame), dtype=bool)
            else:
                threshold = weighted_quantile(direction * inner[score].to_numpy(), weights, q)
                accepted = direction * frame[score].to_numpy() <= threshold
            full = frame.OpenET + accepted * frame.correction
            chosen = frame[accepted]
            curves.append({"score": score, "inner_fraction": float(q),
                           "outer_fraction": float(accepted.mean()),
                           "full_macro_mae": audit.macro_mae(frame.y, full, frame.station.to_numpy()),
                           "selected_neural_mae": float(np.abs(chosen.y - chosen.Full).mean()) if len(chosen) else None,
                           "selected_openet_mae": float(np.abs(chosen.y - chosen.OpenET).mean()) if len(chosen) else None,
                           "rows": len(frame), "selected_rows": int(accepted.sum())})
    return curves


def run_fold(train: pd.DataFrame, test: pd.DataFrame, split: dict,
             columns: list[str], valid_humidity: set[tuple[str, str]]) -> tuple[dict, list[dict], list[dict]]:
    inner_frames = []
    timings = []
    for index, part in enumerate(split["inner_partitions"]):
        fit = train[train.row_id.isin(part["train_row_ids"])]
        val = train[train.row_id.isin(part["validation_row_ids"])]
        network, timing = fit_ensemble(fit[columns].to_numpy(), (fit.y - fit.openet).to_numpy())
        timings.append({"part": "inner", "index": index, **timing})
        mean, spread, distance, seeds = network.predict(val[columns].to_numpy())
        inner = val.copy()
        inner["correction"] = mean
        inner["spread"] = spread
        inner["distance"] = distance
        inner["gain"] = improvement(val.y.to_numpy(), val.openet.to_numpy(), mean)
        inner["inner_fold"] = index
        for j, seed in enumerate(SEEDS):
            inner[f"correction_{seed}"] = seeds[:, j]
        inner_frames.append(inner)
    inner = pd.concat(inner_frames).sort_values("row_id")
    weights = audit.station_weights(inner.station.to_numpy())
    spread_threshold = weighted_quantile(inner.spread.to_numpy(), weights, .95)
    support_threshold = weighted_quantile(inner.distance.to_numpy(), weights, .95)
    features = selector_features(inner.correction.to_numpy(), inner.spread.to_numpy(),
                                 inner.distance.to_numpy(), inner[columns].to_numpy())
    started = time.perf_counter()
    gain_model = HistGradientBoostingRegressor(max_iter=80, learning_rate=.05, max_leaf_nodes=7,
                    min_samples_leaf=50, l2_regularization=10, early_stopping=False, random_state=audit.SEED)
    gain_model.fit(features, inner.gain, sample_weight=weights / weights.mean())
    selector_seconds = time.perf_counter() - started
    inner["predicted_gain"] = gain_model.predict(features)
    losses = {str(q): audit.macro_mae(inner.y, inner.openet + q * inner.correction,
                                    inner.station.to_numpy()) for q in [0, .25, .5, .75, 1]}
    uniform = float(min(losses, key=losses.get))
    network, timing = fit_ensemble(train[columns].to_numpy(), (train.y - train.openet).to_numpy())
    timings.append({"part": "outer", **timing})
    lower = train[columns].quantile(.01).to_numpy()
    upper = train[columns].quantile(.99).to_numpy()
    weather = [i for i, c in enumerate(columns) if c in ["eto", "t_avg", "vpd", "ws"]]
    eligible = np.array([(s, date) in valid_humidity for s, date in zip(test.station, test.date)])
    results = {}
    for condition in ["natural", "probe_clean", "vpd_x10", "wind_x10", "temperature_plus20"]:
        frame = test.copy() if condition == "natural" else test[eligible].copy()
        inputs = frame[columns].to_numpy().copy()
        if condition == "vpd_x10" and "vpd" in columns:
            inputs[:, columns.index("vpd")] *= 10
        if condition == "wind_x10":
            inputs[:, columns.index("ws")] *= 10
        if condition == "temperature_plus20":
            inputs[:, columns.index("t_avg")] += 20
        prediction_start = time.perf_counter()
        mean, spread, distance, seeds = network.predict(inputs)
        score = gain_model.predict(selector_features(mean, spread, distance, inputs))
        masks = {"Full": np.ones(len(frame), dtype=bool), "Spread95": spread <= spread_threshold,
                 "Support95": distance <= support_threshold, "Gain": score > 0,
                 "SupportGain": (distance <= support_threshold) & (score > 0)}
        frame["OpenET"] = frame.openet
        frame["correction"] = mean
        frame["spread"] = spread
        frame["distance"] = distance
        frame["predicted_gain"] = score
        frame["spread_threshold"] = spread_threshold
        frame["support_threshold"] = support_threshold
        for name, mask in masks.items():
            frame[name] = frame.OpenET + mask * mean
            frame["accept_" + name] = mask
        frame["Uniform"] = frame.OpenET + uniform * mean
        clipped = inputs.copy()
        clipped[:, weather] = np.clip(clipped[:, weather], lower[weather], upper[weather])
        frame["Clip"] = frame.OpenET + network.predict(clipped)[0]
        frame["uniform_multiplier"] = uniform
        for j, seed in enumerate(SEEDS):
            frame[f"correction_{seed}"] = seeds[:, j]
        timings.append({"part": "inference", "condition": condition, "rows": len(frame),
                        "predict_seconds": time.perf_counter() - prediction_start})
        frame["fold"] = split["fold"]
        frame["condition"] = condition
        results[condition] = frame
    inner["outer_fold"] = split["fold"]
    inner.to_csv(OUT / f"inner_{split['regime']}_{len(columns)}_{split['fold']}.csv", index=False)
    records = [{"spread_threshold": spread_threshold, "support_threshold": support_threshold,
                "uniform_multiplier": uniform, "uniform_inner_mae": losses,
                "selector_seconds": selector_seconds, "inner_rows": len(inner), "timings": timings}]
    curves = curve_records(results["natural"], inner)
    return results, records, curves


def main() -> None:
    if (OUT / "results.json").exists():
        raise RuntimeError("This experiment already has results; do not overwrite them")
    OUT.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    cohort = pd.read_csv(audit.OUT / "cohort.csv")
    splits = json.loads((audit.OUT / "splits.json").read_text())
    humidity = pd.read_csv(audit.OUT / "humidity_audit.csv")
    valid = set(map(tuple, humidity.loc[humidity.vp_kpa >= 0, ["station", "date"]].to_numpy()))
    results = {}; records = []; curves = []
    for regime in ["proximity", "joint"]:
        for specification, columns in [("archived", audit.FEATURES),
                                        ("noVPD", [c for c in audit.FEATURES if c != "vpd"])]:
            collected = {}
            for split in [s for s in splits if s["regime"] == regime]:
                train = cohort[cohort.row_id.isin(split["train_row_ids"])]
                test = cohort[cohort.row_id.isin(split["test_row_ids"])]
                frames, record, curve = run_fold(train, test, split, columns, valid)
                for condition, frame in frames.items():
                    collected.setdefault(condition, []).append(frame)
                identity = {"regime": regime, "specification": specification, "fold": split["fold"]}
                records.extend([{**identity, **r} for r in record])
                curves.extend([{**identity, **r} for r in curve])
                print(f"{regime} {specification} fold {split['fold']} complete", flush=True)
            key = regime + "_" + specification
            results[key] = {}
            for condition, frames in collected.items():
                frame = pd.concat(frames).sort_values("row_id")
                frame.to_csv(OUT / f"predictions_{key}_{condition}.csv", index=False)
                result = {"rows": len(frame), "stations": frame.station.nunique(),
                          "groups": frame.group.nunique(), "models": evaluate_methods(frame),
                          "croplands": evaluate_methods(frame[frame.landcover == "Croplands"])}
                harm = improvement(frame.y.to_numpy(), frame.OpenET.to_numpy(), frame.correction.to_numpy()) < 0
                result["harm_auc"] = {c: float(roc_auc_score(harm, direction * frame[c]))
                    for c, direction in [("spread", 1), ("distance", 1), ("predicted_gain", -1)]} if len(np.unique(harm)) == 2 else {}
                results[key][condition] = result
                if condition == "natural":
                    name = "predictions" if specification == "archived" else "neural_sensitivity"
                    old = pd.read_csv(audit.OUT / f"{name}_{regime}.csv")
                    model = "ResidualMLP" if specification == "archived" else "ResidualMLP_noVPD"
                    assert frame.row_id.tolist() == old.row_id.tolist()
                    np.testing.assert_allclose(frame.Full, old[model], rtol=1e-10, atol=1e-10)
            if specification == "noVPD":
                clean = pd.read_csv(OUT / f"predictions_{key}_probe_clean.csv")
                fault = pd.read_csv(OUT / f"predictions_{key}_vpd_x10.csv")
                np.testing.assert_array_equal(clean[METHODS].to_numpy(), fault[METHODS].to_numpy())
            (OUT / "progress.json").write_text(json.dumps(results, indent=2))
    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    pd.DataFrame(curves).to_csv(OUT / "coverage_curves.csv", index=False)
    (OUT / "receipt.json").write_text(json.dumps({"seconds": time.perf_counter() - start,
        "code_sha256": audit.sha(Path(__file__)), "audit_code_sha256": audit.sha(Path(audit.__file__)),
        "protocol_sha256": audit.sha(audit.ROOT / "docs/evaluation/ML_SELECTIVE_RESIDUAL_PROTOCOL.md"),
        "cohort_sha256": audit.sha(audit.OUT / "cohort.csv"), "split_sha256": audit.sha(audit.OUT / "splits.json"),
        "versions": {"numpy": np.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__},
        "platform": platform.platform(), "seeds": SEEDS, "records": records}, indent=2))
    print("Selective residual experiment complete.", flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        main()
