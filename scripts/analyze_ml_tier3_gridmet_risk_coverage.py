"""Analyze risk and coverage on frozen Tier 3 predictions."""
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
import analyze_ml_tier1_gridmet as tier1_analysis
import ml_selective_residual as selective
import ml_tier1_gridmet as tier1_runner
import ml_tier1_selective as tier1_selective
import ml_tier3_gridmet as tier3_runner
import ml_transfer_audit as audit

DATA = ROOT / "docs/results/ml_tier3_gridmet"
OUT = ROOT / "docs/results/ml_tier3_gridmet_risk_coverage"
COHORT = ROOT / "docs/results/ml_tier1_gridmet/cohort.csv"
SPLITS = ROOT / "docs/results/ml_tier1_gridmet_10member/splits.json"
TIER3_RECEIPT = DATA / "receipt.json"
SELECTOR_RECEIPT = DATA / "selector_receipt.json"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER3_RISK_COVERAGE_PROTOCOL.md"
METHODS = [
    "Gain", "SupportGain", "MonoGain", "AugmentedGain", "TunedGain",
    "LogisticSign", "ConformalCSR",
]
SCORE_COLUMNS = {
    "Gain": "predicted_gain",
    "MonoGain": "predicted_monotone_gain",
    "AugmentedGain": "predicted_augmented_gain",
    "TunedGain": "tuned_predicted_gain",
    "LogisticSign": "logistic_sign_probability",
}
COVERAGE_LEVELS = np.arange(0.01, 1.001, 0.01)
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20261004
TIE_TOLERANCE = 1e-12


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def station_weights(stations: np.ndarray) -> np.ndarray:
    _, inverse, counts = np.unique(stations, return_inverse=True, return_counts=True)
    return 1.0 / counts[inverse]


def support_score_scales(
    cohort: pd.DataFrame, splits: list[dict]
) -> tuple[dict[int, dict], list[dict]]:
    scales: dict[int, dict] = {}
    fit_records = []
    split_by_year = {int(split["test_year"]): split for split in splits}
    with threadpool_limits(limits=1):
        for year in tier1_runner.TEST_YEARS:
            inner, records = tier3_runner.inner_predictions(
                cohort, split_by_year[year]
            )
            features = tier3_runner.selector_features(inner, "base")
            weights = audit.station_weights(inner.station.to_numpy())
            model = tier1_selective.gain_model()
            model.fit(
                features,
                inner.gain.to_numpy(),
                sample_weight=weights / weights.mean(),
            )
            inner_scores = model.predict(features)
            score_iqr = (
                selective.weighted_quantile(inner_scores, weights, 0.75)
                - selective.weighted_quantile(inner_scores, weights, 0.25)
            )
            distance = inner.distance.to_numpy()
            distance_iqr = (
                selective.weighted_quantile(distance, weights, 0.75)
                - selective.weighted_quantile(distance, weights, 0.25)
            )
            distance_q95 = selective.weighted_quantile(distance, weights, 0.95)
            if not np.isfinite([score_iqr, distance_iqr, distance_q95]).all():
                raise ValueError(f"Year {year} has a nonfinite SupportGain scale")
            if score_iqr <= 0 or distance_iqr <= 0:
                raise ValueError(f"Year {year} has a zero SupportGain scale")
            scales[year] = {
                "gain_score_iqr": float(score_iqr),
                "support_distance_iqr": float(distance_iqr),
                "support_distance_q95": float(distance_q95),
                "inner_rows": int(len(inner)),
                "inner_stations": int(inner.station.nunique()),
            }
            fit_records.append({"test_year": year, "inner_fits": records})
    return scales, fit_records


def add_confidence_scores(
    frame: pd.DataFrame, scales: dict[int, dict], csr_thresholds: dict[int, float]
) -> dict[str, np.ndarray]:
    years = frame.test_year.to_numpy(dtype=int)
    scores = {
        method: frame[column].to_numpy(dtype=float)
        for method, column in SCORE_COLUMNS.items()
    }
    gain_margin = np.empty(len(frame), dtype=float)
    support_margin = np.empty(len(frame), dtype=float)
    csr_score = np.empty(len(frame), dtype=float)
    for year, scale in scales.items():
        selected = years == year
        gain_margin[selected] = (
            frame.loc[selected, "predicted_gain"].to_numpy(dtype=float)
            / scale["gain_score_iqr"]
        )
        support_margin[selected] = (
            scale["support_distance_q95"]
            - frame.loc[selected, "support_distance"].to_numpy(dtype=float)
        ) / scale["support_distance_iqr"]
        csr_score[selected] = 1 - (
            frame.loc[selected, "conformal_width"].to_numpy(dtype=float)
            / csr_thresholds[year]
        )
    scores["SupportGain"] = np.minimum(gain_margin, support_margin)
    scores["ConformalCSR"] = csr_score
    for method, score in scores.items():
        if len(score) != len(frame) or not np.isfinite(score).all():
            raise ValueError(f"{method} has invalid confidence scores")
    return scores


def score_ranking(scores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(-scores, kind="stable")
    ordered_scores = scores[order]
    starts = np.r_[0, np.flatnonzero(np.abs(np.diff(ordered_scores)) > TIE_TOLERANCE) + 1]
    return order, starts


def curve_for_weights(
    scores: np.ndarray,
    losses: np.ndarray,
    weights: np.ndarray,
    levels: np.ndarray = COVERAGE_LEVELS,
    ranking: tuple[np.ndarray, np.ndarray] | None = None,
) -> np.ndarray:
    order, starts = ranking if ranking is not None else score_ranking(scores)
    block_weights = np.add.reduceat(weights[order], starts)
    block_losses = np.add.reduceat(weights[order] * losses[order], starts)
    cumulative_weights = np.cumsum(block_weights)
    cumulative_losses = np.cumsum(block_losses)
    targets = levels * cumulative_weights[-1]
    boundary = np.searchsorted(cumulative_weights, targets, side="left")
    previous_weights = np.zeros(len(levels), dtype=float)
    previous_losses = np.zeros(len(levels), dtype=float)
    has_previous = boundary > 0
    previous_weights[has_previous] = cumulative_weights[boundary[has_previous] - 1]
    previous_losses[has_previous] = cumulative_losses[boundary[has_previous] - 1]
    fractions = (targets - previous_weights) / block_weights[boundary]
    accepted_loss = previous_losses + fractions * block_losses[boundary]
    return accepted_loss / targets


def bootstrap_curves(
    scores: dict[str, np.ndarray],
    losses: np.ndarray,
    base_weights: np.ndarray,
    group_index: np.ndarray,
    group_count: int,
    seed: int,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    rankings = {method: score_ranking(scores[method]) for method in METHODS}
    draws = {method: np.empty((BOOTSTRAP_DRAWS, len(COVERAGE_LEVELS))) for method in METHODS}
    for draw in range(BOOTSTRAP_DRAWS):
        sampled = rng.integers(0, group_count, size=group_count)
        multiplicity = np.bincount(sampled, minlength=group_count)
        weights = base_weights * multiplicity[group_index]
        for method in METHODS:
            draws[method][draw] = curve_for_weights(
                scores[method], losses, weights, ranking=rankings[method]
            )
    return draws


def fixed_metrics(
    frame: pd.DataFrame, method: str, accepted: np.ndarray, base_weights: np.ndarray
) -> dict:
    loss = np.abs(frame.openet.to_numpy() + frame.correction.to_numpy() - frame.y.to_numpy())
    accepted_weight = base_weights * accepted
    total_weight = base_weights.sum()
    selected_weight = accepted_weight.sum()
    end_to_end_loss = np.abs(frame[method].to_numpy() - frame.y.to_numpy())
    return {
        "fixed_coverage": float(selected_weight / total_weight),
        "fixed_selective_mae_mm_day": (
            float(np.sum(accepted_weight * loss) / selected_weight)
            if selected_weight > 0 else None
        ),
        "fixed_end_to_end_station_macro_mae_mm_day": float(
            np.sum(base_weights * end_to_end_loss) / total_weight
        ),
        "accepted_rows": int(accepted.sum()),
    }


def analyze() -> dict:
    started = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    if not TIER3_RECEIPT.is_file() or not SELECTOR_RECEIPT.is_file():
        raise RuntimeError("The frozen Tier 3 run is incomplete")
    cohort = pd.read_csv(COHORT, parse_dates=["date"])
    splits = json.loads(SPLITS.read_text())
    selector_records = json.loads(SELECTOR_RECEIPT.read_text())
    scale_cache_path = OUT / "support_score_scales.json"
    scale_sources = [
        PROTOCOL,
        COHORT,
        SPLITS,
        ROOT / "scripts/ml_tier3_gridmet.py",
        ROOT / "scripts/ml_tier1_gridmet.py",
        ROOT / "scripts/ml_tier1_selective.py",
        ROOT / "scripts/ml_selective_residual.py",
        ROOT / "scripts/ml_transfer_audit.py",
        ROOT / "scripts/analyze_ml_tier1_gridmet.py",
    ]
    scale_source_hashes = {
        str(path.relative_to(ROOT)): sha256(path) for path in scale_sources
    }
    runtime_versions = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
    }
    scale_cache_hit = False
    if scale_cache_path.is_file():
        cached = json.loads(scale_cache_path.read_text())
        if (
            cached.get("source_sha256") == scale_source_hashes
            and cached.get("runtime_versions") == runtime_versions
        ):
            scales = {int(year): value for year, value in cached["scales"].items()}
            inner_records = cached["inner_fit_records"]
            scale_cache_hit = True
        else:
            scales, inner_records = support_score_scales(cohort, splits)
    else:
        scales, inner_records = support_score_scales(cohort, splits)
    if not scale_cache_hit:
        scale_cache_path.write_text(json.dumps({
            "source_sha256": scale_source_hashes,
            "runtime_versions": runtime_versions,
            "scales": scales,
            "inner_fit_records": inner_records,
        }, indent=2) + "\n")
    csr_thresholds = {
        int(record["test_year"]): float(record["conformal"]["threshold"])
        for record in selector_records
    }
    if set(csr_thresholds) != set(scales):
        raise ValueError("Conformal thresholds do not cover every test year")
    for year, threshold in csr_thresholds.items():
        if not np.isfinite(threshold) or threshold <= 0:
            raise ValueError(f"Year {year} has an invalid conformal threshold")

    curve_rows = []
    aurc_rows = []
    fixed_rows = []
    support_check_rows = []
    expected_row_ids = None
    expected_groups = None
    for condition_index, condition in enumerate(tier1_analysis.CONDITIONS):
        frame = pd.read_csv(DATA / f"predictions_{condition}.csv")
        frame = frame.sort_values("row_id").reset_index(drop=True)
        row_ids = frame.row_id.to_numpy()
        if expected_row_ids is None:
            expected_row_ids = row_ids
            expected_groups = np.sort(frame.group.unique())
        elif not np.array_equal(row_ids, expected_row_ids):
            raise ValueError(f"{condition} uses different outer rows")
        if not np.array_equal(np.sort(frame.group.unique()), expected_groups):
            raise ValueError(f"{condition} uses different spatial groups")

        base_weights = station_weights(frame.station.to_numpy())
        group_names, group_index = np.unique(frame.group.to_numpy(), return_inverse=True)
        losses = np.abs(
            frame.openet.to_numpy(dtype=float)
            + frame.correction.to_numpy(dtype=float)
            - frame.y.to_numpy(dtype=float)
        )
        scores = add_confidence_scores(frame, scales, csr_thresholds)
        inferred_support = scores["SupportGain"] > 0
        saved_support = frame.accept_SupportGain.to_numpy(dtype=bool)
        support_ties = (
            (frame.support_distance.to_numpy(dtype=float)
             == np.array([scales[int(year)]["support_distance_q95"] for year in frame.test_year]))
            & (frame.predicted_gain.to_numpy(dtype=float) > 0)
        )
        mismatch = inferred_support != saved_support
        if np.any(mismatch & ~support_ties):
            raise ValueError(f"SupportGain score does not match its saved gate: {condition}")
        support_check_rows.append({
            "condition": condition,
            "score_gate_mismatches": int(mismatch.sum()),
            "allowed_zero_margin_ties": int((mismatch & support_ties).sum()),
        })

        bootstrap = bootstrap_curves(
            scores, losses, base_weights, group_index, len(group_names),
            BOOTSTRAP_SEED + condition_index,
        )
        for method in METHODS:
            point = curve_for_weights(scores[method], losses, base_weights)
            draws = bootstrap[method]
            low, high = np.quantile(draws, [0.025, 0.975], axis=0)
            for level, risk, ci_low, ci_high in zip(COVERAGE_LEVELS, point, low, high):
                curve_rows.append({
                    "condition": condition,
                    "method": method,
                    "coverage": float(level),
                    "selective_mae_mm_day": float(risk),
                    "ci95_low_mm_day": float(ci_low),
                    "ci95_high_mm_day": float(ci_high),
                })
            aurc_draws = draws.mean(axis=1)
            aurc_low, aurc_high = np.quantile(aurc_draws, [0.025, 0.975])
            aurc = float(point.mean())
            aurc_rows.append({
                "condition": condition,
                "method": method,
                "aurc_mm_day": aurc,
                "ci95_low_mm_day": float(aurc_low),
                "ci95_high_mm_day": float(aurc_high),
                "bootstrap_draws": BOOTSTRAP_DRAWS,
                "bootstrap_seed": BOOTSTRAP_SEED + condition_index,
            })
            accepted = frame[f"accept_{method}"].to_numpy(dtype=bool)
            fixed_rows.append({
                "condition": condition,
                "method": method,
                **fixed_metrics(frame, method, accepted, base_weights),
            })

    curve_path = OUT / "risk_coverage_curves.csv"
    aurc_path = OUT / "aurc_summary.csv"
    fixed_path = OUT / "fixed_operating_points.csv"
    support_path = OUT / "support_score_check.csv"
    pd.DataFrame(curve_rows).to_csv(curve_path, index=False)
    pd.DataFrame(aurc_rows).to_csv(aurc_path, index=False)
    pd.DataFrame(fixed_rows).to_csv(fixed_path, index=False)
    pd.DataFrame(support_check_rows).to_csv(support_path, index=False)

    input_paths = [
        PROTOCOL, COHORT, SPLITS, TIER3_RECEIPT, SELECTOR_RECEIPT,
        DATA / "results.json", Path(__file__),
        ROOT / "scripts/ml_tier3_gridmet.py",
        ROOT / "scripts/ml_tier1_gridmet.py",
        ROOT / "scripts/ml_tier1_selective.py",
        ROOT / "scripts/ml_selective_residual.py",
        ROOT / "scripts/ml_transfer_audit.py",
        ROOT / "scripts/analyze_ml_tier1_gridmet.py",
    ] + [DATA / f"predictions_{condition}.csv" for condition in tier1_analysis.CONDITIONS]
    receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "analysis_script_sha256": sha256(Path(__file__)),
        "input_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in input_paths},
        "output_sha256": {
            curve_path.name: sha256(curve_path),
            aurc_path.name: sha256(aurc_path),
            fixed_path.name: sha256(fixed_path),
            support_path.name: sha256(support_path),
            scale_cache_path.name: sha256(scale_cache_path),
        },
        "conditions": tier1_analysis.CONDITIONS,
        "methods": METHODS,
        "rows": int(len(expected_row_ids)),
        "stations": int(pd.read_csv(DATA / "predictions_clean.csv").station.nunique()),
        "groups": int(len(expected_groups)),
        "bootstrap_draws_per_condition": BOOTSTRAP_DRAWS,
        "bootstrap_seed_base": BOOTSTRAP_SEED,
        "coverage_levels": [float(value) for value in COVERAGE_LEVELS],
        "tie_tolerance_score_units": TIE_TOLERANCE,
        "support_score_scales_by_year": scales,
        "support_score_cache_hit": scale_cache_hit,
        "support_gate_check": support_check_rows,
        "inner_fit_records": inner_records,
        "runtime_seconds": time.perf_counter() - started,
        "runtime_note": "One run. No timing interval was measured.",
        **runtime_versions,
    }
    receipt_path = OUT / "analysis_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({
        "protocol_sha256": receipt["protocol_sha256"],
        "analysis_script_sha256": receipt["analysis_script_sha256"],
        "rows": receipt["rows"],
        "stations": receipt["stations"],
        "groups": receipt["groups"],
        "conditions": len(receipt["conditions"]),
        "methods": receipt["methods"],
        "bootstrap_draws_per_condition": receipt["bootstrap_draws_per_condition"],
        "support_score_cache_hit": receipt["support_score_cache_hit"],
        "runtime_seconds": receipt["runtime_seconds"],
        "output_sha256": receipt["output_sha256"],
    }, indent=2))
    return receipt


if __name__ == "__main__":
    analyze()
