"""Extend the exploratory spatial holdout to all five group folds."""
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
import ml_tier1_gridmet as gridmet
import ml_tier1_selective as tier1
import ml_transfer_audit as audit
import run_ml_tier1_spatial_holdout as spatial

OUT = ROOT / "docs/results/ml_tier1_spatial_holdout_sensitivity"
COHORT = ROOT / "docs/results/ml_tier1_gridmet/cohort.csv"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_SPATIAL_HOLDOUT_SENSITIVITY.md"
SOURCE_RESULTS = spatial.OUT


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_fold(cohort: pd.DataFrame, index: int, groups: list[str]) -> tuple:
    train_groups, test_groups = audit.field_withheld_folds(
        groups, 5, spatial.OUTER_SEED
    )[index]
    train = cohort.loc[cohort.group.isin(train_groups)].copy()
    test = cohort.loc[cohort.group.isin(test_groups)].copy()
    if set(train_groups) & set(test_groups):
        raise ValueError("An outer group appears in both partitions")
    if set(train.station) & set(test.station):
        raise ValueError("An outer test station also appears in training")
    if len(train) + len(test) != len(cohort):
        raise ValueError("The outer split does not cover the cohort")
    split_record = {
        "fold": index,
        "train_groups": train_groups,
        "test_groups": test_groups,
        "train_row_ids": train.row_id.astype(int).tolist(),
        "test_row_ids": test.row_id.astype(int).tolist(),
    }
    return train, test, split_record


def load_fold_zero(test: pd.DataFrame) -> tuple[dict, dict]:
    run_receipt_path = SOURCE_RESULTS / "run_receipt.json"
    split_path = SOURCE_RESULTS / "splits.json"
    if not run_receipt_path.is_file() or not split_path.is_file():
        raise FileNotFoundError("The original fold-zero result is incomplete")
    receipt = json.loads(run_receipt_path.read_text())
    split = json.loads(split_path.read_text())
    if receipt["protocol_sha256"] != sha256(spatial.PROTOCOL):
        raise ValueError("The original fold-zero protocol hash does not match")
    if receipt["cohort_sha256"] != sha256(COHORT):
        raise ValueError("The original fold-zero cohort hash does not match")
    if receipt["script_sha256"] != sha256(
        ROOT / "scripts/run_ml_tier1_spatial_holdout.py"
    ):
        raise ValueError("The original fold-zero code hash does not match")
    if split["test_row_ids"] != test.row_id.astype(int).tolist():
        raise ValueError("The saved fold-zero rows do not match the split")
    predictions = {}
    for condition in spatial.PRIMARY_CONDITIONS:
        path = SOURCE_RESULTS / f"predictions_{condition}.csv"
        if not path.is_file():
            raise FileNotFoundError(f"The fold-zero prediction is missing: {path}")
        frame = pd.read_csv(path, parse_dates=["date"]).sort_values("row_id")
        if frame.row_id.astype(int).tolist() != test.row_id.astype(int).tolist():
            raise ValueError("The fold-zero predictions do not match the test rows")
        predictions[condition] = frame
    return predictions, {
        "reused": True,
        "source_protocol_sha256": receipt["protocol_sha256"],
        "source_script_sha256": receipt["script_sha256"],
        "source_run_receipt_sha256": sha256(run_receipt_path),
        "source_analysis_receipt_sha256": sha256(
            SOURCE_RESULTS / "analysis_receipt.json"
        ),
        "source_prediction_sha256": {
            condition: sha256(
                SOURCE_RESULTS / f"predictions_{condition}.csv"
            )
            for condition in spatial.PRIMARY_CONDITIONS
        },
    }


def build_figure(summary: dict) -> dict:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "font.size": 12,
            "axes.linewidth": 1.8,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.labelcolor": "#333333",
            "text.color": "#222222",
            "legend.frameon": False,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
        }
    )
    conditions = spatial.PRIMARY_CONDITIONS
    labels = [spatial.CONDITION_LABELS[name] for name in conditions]
    positions = np.arange(len(conditions))
    results = summary["conditions"]
    effects = np.array(
        [results[name]["gain_minus_supportgain_mm_day"] for name in conditions]
    )
    intervals = np.array(
        [results[name]["simultaneous_ci95_mm_day"] for name in conditions]
    )
    errors = np.vstack([effects - intervals[:, 0], intervals[:, 1] - effects])
    gain_coverage = [
        100 * results[name]["gain_station_weighted_acceptance"]
        for name in conditions
    ]
    support_coverage = [
        100 * results[name]["supportgain_station_weighted_acceptance"]
        for name in conditions
    ]
    figure, axes = plt.subplots(
        2, 1, figsize=(9.2, 6.0), sharex=True,
        gridspec_kw={"height_ratios": [1.25, 1]},
    )
    effect_axis, coverage_axis = axes
    effect_axis.errorbar(
        positions,
        effects,
        yerr=errors,
        fmt="o",
        color=spatial.BLUE,
        ecolor=spatial.NEUTRAL,
        elinewidth=1.6,
        capsize=4,
        markersize=6,
    )
    effect_axis.axhline(0, color=spatial.NEUTRAL, linewidth=1.1)
    effect_axis.set_ylabel("Gain MAE minus SupportGain MAE (mm/day)")
    effect_axis.set_title(
        "SupportGain on five held-out spatial folds", loc="left"
    )
    effect_axis.grid(axis="y", color="#E5E5E5", linewidth=0.8)
    effect_axis.set_axisbelow(True)
    effect_axis.text(
        0.99,
        0.97,
        "Simultaneous 95% group-bootstrap intervals",
        transform=effect_axis.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        color="#4D4D4D",
    )
    coverage_axis.plot(
        positions,
        gain_coverage,
        marker="o",
        color=spatial.RED,
        linewidth=1.8,
        label="Gain",
    )
    coverage_axis.plot(
        positions,
        support_coverage,
        marker="o",
        color=spatial.BLUE,
        linewidth=1.8,
        label="SupportGain",
    )
    coverage_axis.set_ylabel("Station-weighted acceptance (%)")
    coverage_axis.set_ylim(0, 105)
    coverage_axis.set_xticks(positions, labels, rotation=12, ha="right")
    coverage_axis.grid(axis="y", color="#E5E5E5", linewidth=0.8)
    coverage_axis.set_axisbelow(True)
    coverage_axis.legend(loc="upper center", ncol=2)
    figure.tight_layout(pad=1.2)

    figure_directory = ROOT / "manuscript/arxiv/figures"
    figure_directory.mkdir(parents=True, exist_ok=True)
    stem = "figure_23_tier1_spatial_holdout_sensitivity"
    pdf_path = figure_directory / f"{stem}.pdf"
    png_path = figure_directory / f"{stem}.png"
    figure.savefig(pdf_path, bbox_inches="tight", facecolor="white")
    figure.savefig(png_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return {
        "reference": (
            "https://github.com/ChenLiu-1996/figures4papers/"
            "blob/main/scientific-figure-making/SKILL.md"
        ),
        "pdf_sha256": sha256(pdf_path),
        "png_sha256": sha256(png_path),
    }


def run() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise RuntimeError(f"Refusing to overwrite completed results in {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    cohort = pd.read_csv(COHORT, parse_dates=["date"])
    if (
        len(cohort) != 16366
        or cohort.station.nunique() != 151
        or cohort.group.nunique() != 102
    ):
        raise ValueError("The cohort does not match the frozen protocol")
    groups = sorted(cohort.group.unique())
    prediction_folds = {
        condition: [] for condition in spatial.PRIMARY_CONDITIONS
    }
    fold_splits = []
    fold_records = []
    for fold_index in range(5):
        train, test, split_record = make_fold(cohort, fold_index, groups)
        fold_splits.append(split_record)
        fold_directory = OUT / f"fold_{fold_index}"
        fold_directory.mkdir(parents=True, exist_ok=True)
        if fold_index == 0:
            predictions, record = load_fold_zero(test)
        else:
            inner_split = spatial.make_inner_split(train, fold=fold_index)
            inner, augmented, inner_fits = gridmet.inner_training(
                train, inner_split, audit.FEATURES
            )
            selectors = tier1.fit_selectors(
                inner, augmented, audit.FEATURES
            )
            network, outer_fit = gridmet.fit_gridmet_ensemble(
                train[audit.FEATURES].to_numpy(),
                (train.y - train.openet).to_numpy(),
            )
            all_predictions = tier1.infer(
                test, network, selectors, train, audit.FEATURES
            )
            predictions = {
                condition: all_predictions[condition].sort_values("row_id")
                for condition in spatial.PRIMARY_CONDITIONS
            }
            record = {
                "reused": False,
                "inner_fits": inner_fits,
                "outer_fit": outer_fit,
            }
        for condition, frame in predictions.items():
            expected = test.row_id.astype(int).tolist()
            if frame.row_id.astype(int).tolist() != expected:
                raise ValueError(
                    f"Fold {fold_index} predictions do not match the test rows"
                )
            frame = frame.copy()
            frame["outer_fold"] = fold_index
            frame.to_csv(
                fold_directory / f"predictions_{condition}.csv", index=False
            )
            prediction_folds[condition].append(frame)
        fold_records.append(
            {
                "fold": fold_index,
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "train_stations": int(train.station.nunique()),
                "test_stations": int(test.station.nunique()),
                "train_groups": int(train.group.nunique()),
                "test_groups": int(test.group.nunique()),
                **record,
            }
        )
        print(f"Spatial fold {fold_index} complete.", flush=True)

    combined = {}
    for condition, fold_frames in prediction_folds.items():
        frame = pd.concat(fold_frames, ignore_index=True).sort_values("row_id")
        if frame.row_id.duplicated().any() or len(frame) != len(cohort):
            raise ValueError("Each cohort row must have one held-out prediction")
        if frame.row_id.astype(int).tolist() != cohort.row_id.astype(int).tolist():
            raise ValueError("The pooled prediction rows do not match the cohort")
        frame.to_csv(OUT / f"predictions_{condition}.csv", index=False)
        combined[condition] = frame

    summary, group_deltas = spatial.summarize_conditions(combined)
    result_path = OUT / "results.json"
    result_path.write_text(json.dumps(summary, indent=2) + "\n")
    group_delta_path = OUT / "group_deltas.csv"
    group_deltas.to_csv(group_delta_path, index=False)
    split_path = OUT / "splits.json"
    split_path.write_text(json.dumps(fold_splits, indent=2) + "\n")
    run_receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "script_sha256": sha256(Path(__file__)),
        "cohort_sha256": sha256(COHORT),
        "split_sha256": sha256(split_path),
        "outer_seed": spatial.OUTER_SEED,
        "inner_seed": spatial.INNER_SEED,
        "neural_seeds": gridmet.NEURAL_SEEDS,
        "versions": {
            "python": sys.version,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "platform": platform.platform(),
        "rows": int(len(cohort)),
        "stations": int(cohort.station.nunique()),
        "groups": int(cohort.group.nunique()),
        "folds": fold_records,
        "source_fold_zero_receipt_sha256": sha256(
            SOURCE_RESULTS / "run_receipt.json"
        ),
        "seconds": time.perf_counter() - started,
    }
    run_receipt_path = OUT / "run_receipt.json"
    run_receipt_path.write_text(json.dumps(run_receipt, indent=2) + "\n")
    figure = build_figure(summary)
    analysis_receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "script_sha256": sha256(Path(__file__)),
        "cohort_sha256": sha256(COHORT),
        "run_receipt_sha256": sha256(run_receipt_path),
        "results_sha256": sha256(result_path),
        "group_deltas_sha256": sha256(group_delta_path),
        "prediction_sha256": {
            condition: sha256(OUT / f"predictions_{condition}.csv")
            for condition in spatial.PRIMARY_CONDITIONS
        },
        "figure": figure,
    }
    (OUT / "analysis_receipt.json").write_text(
        json.dumps(analysis_receipt, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2), flush=True)
    print("Five-fold spatial holdout sensitivity complete.", flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        run()
