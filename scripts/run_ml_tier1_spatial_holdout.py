"""Run a fixed spatial holdout audit for Gain and SupportGain."""
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

OUT = ROOT / "docs/results/ml_tier1_spatial_holdout"
COHORT = ROOT / "docs/results/ml_tier1_gridmet/cohort.csv"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_SPATIAL_HOLDOUT_PROTOCOL.md"
OUTER_SEED = 20261006
INNER_SEED = 20261007
BOOTSTRAP_SEED = 20261060
BOOTSTRAP_DRAWS = 2000
PRIMARY_CONDITIONS = [
    "clean",
    "wind_x2.237",
    "wind_x3.6",
    "temperature_fahrenheit_as_celsius",
    "vpd_x10",
]
CONDITION_LABELS = {
    "clean": "Clean",
    "wind_x2.237": "Wind x2.237",
    "wind_x3.6": "Wind x3.6",
    "temperature_fahrenheit_as_celsius": "Fahrenheit as Celsius",
    "vpd_x10": "VPD x10",
}
BLUE = "#0F4D92"
RED = "#B64342"
NEUTRAL = "#4D4D4D"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_inner_split(train: pd.DataFrame, fold: int) -> dict:
    groups = sorted(train.group.unique())
    if len(groups) < 3:
        raise ValueError("The outer training set has fewer than three groups")
    partitions = []
    for fit_groups, validation_groups in audit.field_withheld_folds(
        groups, 3, INNER_SEED
    ):
        if set(fit_groups) & set(validation_groups):
            raise ValueError("An inner group appears in both partitions")
        fit = train.loc[train.group.isin(fit_groups), "row_id"].astype(int).tolist()
        validation = train.loc[
            train.group.isin(validation_groups), "row_id"
        ].astype(int).tolist()
        partitions.append(
            {
                "train_groups": fit_groups,
                "validation_groups": validation_groups,
                "train_row_ids": fit,
                "validation_row_ids": validation,
            }
        )
    return {"fold": fold, "inner_partitions": partitions}


def paired_station_deltas(frame: pd.DataFrame) -> pd.DataFrame:
    values = frame.assign(
        delta=np.abs(frame.y - frame.Gain)
        - np.abs(frame.y - frame.SupportGain)
    )
    return (
        values.groupby(["group", "station"], sort=True)
        .delta.mean()
        .reset_index()
    )


def summarize_conditions(
    frames: dict[str, pd.DataFrame],
) -> tuple[dict, pd.DataFrame]:
    per_condition = {
        condition: paired_station_deltas(frame)
        for condition, frame in frames.items()
    }
    groups = sorted(frames[PRIMARY_CONDITIONS[0]].group.unique())
    if any(
        sorted(frame.group.unique()) != groups
        for frame in frames.values()
    ):
        raise ValueError("Primary conditions do not share the same test groups")
    group_counts = (
        per_condition[PRIMARY_CONDITIONS[0]]
        .groupby("group", sort=True)
        .station.count()
        .reindex(groups)
        .to_numpy()
    )
    group_sums = {}
    group_rows = []
    points = {}
    for condition, station in per_condition.items():
        grouped = station.groupby("group", sort=True).delta.agg(["sum", "count"])
        grouped = grouped.reindex(groups)
        if not np.array_equal(grouped["count"].to_numpy(), group_counts):
            raise ValueError("Spatial groups have different station counts")
        group_sums[condition] = grouped["sum"].to_numpy()
        points[condition] = float(station.delta.mean())
        for group, row in grouped.iterrows():
            group_rows.append(
                {
                    "condition": condition,
                    "group": group,
                    "stations": int(row["count"]),
                    "gain_minus_supportgain_mm_day": float(
                        row["sum"] / row["count"]
                    ),
                }
            )

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    samples = rng.integers(
        0, len(groups), size=(BOOTSTRAP_DRAWS, len(groups))
    )
    draws = {}
    for condition in PRIMARY_CONDITIONS:
        sums = group_sums[condition]
        numerator = sums[samples].sum(axis=1)
        denominator = group_counts[samples].sum(axis=1)
        draws[condition] = numerator / denominator

    standard_errors = {
        condition: float(np.std(values, ddof=1))
        for condition, values in draws.items()
    }
    if any(not np.isfinite(value) or value <= 0 for value in standard_errors.values()):
        raise ValueError("A bootstrap standard error is not positive and finite")
    standardized = np.column_stack(
        [
            (draws[condition] - points[condition])
            / standard_errors[condition]
            for condition in PRIMARY_CONDITIONS
        ]
    )
    max_statistic = np.max(np.abs(standardized), axis=1)
    critical_value = float(np.quantile(max_statistic, 0.95))

    summary = {}
    for condition, frame in frames.items():
        gain_acceptance = float(
            frame.groupby("station").accept_Gain.mean().mean()
        )
        support_acceptance = float(
            frame.groupby("station").accept_SupportGain.mean().mean()
        )
        marginal_low, marginal_high = np.quantile(
            draws[condition], [0.025, 0.975]
        )
        simultaneous_half_width = (
            critical_value * standard_errors[condition]
        )
        summary[condition] = {
            "label": CONDITION_LABELS[condition],
            "rows": int(len(frame)),
            "stations": int(frame.station.nunique()),
            "groups": int(frame.group.nunique()),
            "gain_station_macro_mae_mm_day": audit.macro_mae(
                frame.y.to_numpy(), frame.Gain.to_numpy(),
                frame.station.to_numpy(),
            ),
            "supportgain_station_macro_mae_mm_day": audit.macro_mae(
                frame.y.to_numpy(), frame.SupportGain.to_numpy(),
                frame.station.to_numpy(),
            ),
            "gain_minus_supportgain_mm_day": points[condition],
            "marginal_ci95_mm_day": [
                float(marginal_low), float(marginal_high)
            ],
            "simultaneous_ci95_mm_day": [
                float(points[condition] - simultaneous_half_width),
                float(points[condition] + simultaneous_half_width),
            ],
            "gain_station_weighted_acceptance": gain_acceptance,
            "supportgain_station_weighted_acceptance": support_acceptance,
            "groups_favoring_supportgain": int(
                (
                    per_condition[condition]
                    .groupby("group")
                    .delta.mean()
                    .reindex(groups)
                    > 0
                ).sum()
            ),
        }
    return (
        {
            "status": "exploratory_spatial_holdout",
            "difference": "Gain MAE minus SupportGain MAE",
            "positive_favors": "SupportGain",
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "simultaneous_family_size": len(PRIMARY_CONDITIONS),
            "simultaneous_critical_value": critical_value,
            "p_value": None,
            "conditions": summary,
        },
        pd.DataFrame(group_rows),
    )


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
    conditions = PRIMARY_CONDITIONS
    labels = [CONDITION_LABELS[name] for name in conditions]
    positions = np.arange(len(conditions))
    results = summary["conditions"]
    effects = np.array(
        [results[name]["gain_minus_supportgain_mm_day"] for name in conditions]
    )
    intervals = np.array(
        [results[name]["simultaneous_ci95_mm_day"] for name in conditions]
    )
    lower = effects - intervals[:, 0]
    upper = intervals[:, 1] - effects
    gain_acceptance = [
        100 * results[name]["gain_station_weighted_acceptance"]
        for name in conditions
    ]
    support_acceptance = [
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
        yerr=np.vstack([lower, upper]),
        fmt="o",
        color=BLUE,
        ecolor=NEUTRAL,
        elinewidth=1.6,
        capsize=4,
        markersize=6,
    )
    effect_axis.axhline(0, color=NEUTRAL, linewidth=1.1)
    effect_axis.set_ylabel("Gain MAE minus SupportGain MAE (mm/day)")
    effect_axis.set_title(
        "Selector performance on held-out spatial groups", loc="left"
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
        gain_acceptance,
        marker="o",
        color=RED,
        linewidth=1.8,
        label="Gain",
    )
    coverage_axis.plot(
        positions,
        support_acceptance,
        marker="o",
        color=BLUE,
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
    stem = "figure_22_tier1_spatial_holdout"
    pdf_path = figure_directory / f"{stem}.pdf"
    png_path = figure_directory / f"{stem}.png"
    figure.savefig(pdf_path, bbox_inches="tight", facecolor="white")
    figure.savefig(
        png_path, dpi=300, bbox_inches="tight", facecolor="white"
    )
    plt.close(figure)
    return {
        "reference": (
            "https://github.com/ChenLiu-1996/figures4papers/"
            "blob/main/scientific-figure-making/SKILL.md"
        ),
        "design": (
            "Adapted Helvetica fallback, blue and red method roles, "
            "minimal spines, grouped interval panel, and vector PDF export."
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
        raise ValueError("The cohort does not match the fixed protocol")
    columns = audit.FEATURES
    groups = sorted(cohort.group.unique())
    train_groups, test_groups = audit.field_withheld_folds(
        groups, 5, OUTER_SEED
    )[0]
    if set(train_groups) & set(test_groups):
        raise ValueError("An outer group appears in both partitions")
    train = cohort.loc[cohort.group.isin(train_groups)].copy()
    test = cohort.loc[cohort.group.isin(test_groups)].copy()
    if set(train.station) & set(test.station):
        raise ValueError("An outer test station also appears in training")
    if len(train) + len(test) != len(cohort):
        raise ValueError("The outer split does not cover the cohort")

    split = make_inner_split(train, fold=0)
    inner, augmented, inner_fits = gridmet.inner_training(
        train, split, columns
    )
    selectors = tier1.fit_selectors(inner, augmented, columns)
    network, outer_fit = gridmet.fit_gridmet_ensemble(
        train[columns].to_numpy(),
        (train.y - train.openet).to_numpy(),
    )
    all_predictions = tier1.infer(test, network, selectors, train, columns)
    frames = {
        condition: all_predictions[condition].sort_values("row_id")
        for condition in PRIMARY_CONDITIONS
    }
    for condition, frame in frames.items():
        frame.to_csv(OUT / f"predictions_{condition}.csv", index=False)

    summary, group_deltas = summarize_conditions(frames)
    result_path = OUT / "results.json"
    result_path.write_text(json.dumps(summary, indent=2) + "\n")
    group_delta_path = OUT / "group_deltas.csv"
    group_deltas.to_csv(group_delta_path, index=False)
    split_record = {
        "outer_seed": OUTER_SEED,
        "inner_seed": INNER_SEED,
        "train_groups": train_groups,
        "test_groups": test_groups,
        "train_row_ids": train.row_id.astype(int).tolist(),
        "test_row_ids": test.row_id.astype(int).tolist(),
        "inner_partitions": split["inner_partitions"],
    }
    split_path = OUT / "splits.json"
    split_path.write_text(json.dumps(split_record, indent=2) + "\n")
    run_receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "script_sha256": sha256(Path(__file__)),
        "cohort_sha256": sha256(COHORT),
        "split_sha256": sha256(split_path),
        "outer_seed": OUTER_SEED,
        "inner_seed": INNER_SEED,
        "neural_seeds": gridmet.NEURAL_SEEDS,
        "versions": {
            "python": sys.version,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "platform": platform.platform(),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_stations": int(train.station.nunique()),
        "test_stations": int(test.station.nunique()),
        "train_groups": int(train.group.nunique()),
        "test_groups": int(test.group.nunique()),
        "inner_fits": inner_fits,
        "outer_fit": outer_fit,
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
            for condition in PRIMARY_CONDITIONS
        },
        "figure": figure,
    }
    (OUT / "analysis_receipt.json").write_text(
        json.dumps(analysis_receipt, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2), flush=True)
    print("Spatial holdout audit complete.", flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=1):
        run()
