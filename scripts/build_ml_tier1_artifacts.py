"""Build Tier 1 figures and paired comparison summaries."""
# Figure layout and palette follow figures4papers scientific-figure-making.
# Source: https://github.com/ChenLiu-1996/figures4papers
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ml_transfer_audit as audit
import ml_tier1_selective as experiment

DATA = ROOT / "docs/results/ml_tier1_selective"
FIG = ROOT / "manuscript/arxiv/figures"
OUT = DATA
COLORS = {
    "OpenET": "#4D4D4D", "Full": "#CFCECE", "Spread95": "#FFD700",
    "Support95": "#B64342", "Gain": "#E9A6A1", "SupportGain": "#0F4D92",
    "MonoGain": "#9A4D8E", "AugmentedGain": "#8BCF8B", "Uniform": "#42949E",
    "LocalShrinkage": "#3775BA", "Clip": "#767676",
}
plt.rcParams.update({
    "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
    "font.size": 10, "axes.linewidth": 1.2,
    "axes.spines.right": False, "axes.spines.top": False,
    "axes.labelcolor": "#333333", "text.color": "#222222",
    "legend.frameon": False, "pdf.fonttype": 42, "svg.fonttype": "none",
})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_figure(fig, name: str, *, legend_space: float = 0) -> None:
    fig.tight_layout(pad=1.2, rect=(0, legend_space, 1, 1))
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(FIG / f"{name}.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def read_predictions(condition: str) -> pd.DataFrame:
    return pd.read_csv(DATA / f"predictions_{condition}.csv")


def score_series(conditions: list[str]) -> tuple[dict, dict]:
    performance = {name: [] for name in experiment.METHODS}
    acceptance = {name: [] for name in experiment.METHODS}
    for condition in conditions:
        frame = read_predictions(condition)
        for name in experiment.METHODS:
            performance[name].append(
                audit.macro_mae(frame.y.to_numpy(), frame[name].to_numpy(), frame.station.to_numpy())
            )
            column = f"accept_{name}"
            if column in frame:
                acceptance[name].append(float(frame.groupby("station")[column].mean().mean()))
            elif name == "OpenET":
                acceptance[name].append(0.0)
            elif name in {"Full", "Clip"}:
                acceptance[name].append(1.0)
            else:
                acceptance[name].append(float((frame[name] != frame.OpenET).mean()))
    return performance, acceptance


def trend_figure() -> None:
    wind_conditions = ["wind_x0", "wind_x0.447", "wind_x1", "wind_x2.237", "wind_x3.6", "wind_x5", "wind_x10"]
    temperature_conditions = ["clean", "temperature_plus5", "temperature_plus10", "temperature_plus20", "temperature_plus32", "temperature_fahrenheit_as_celsius"]
    wind_performance, wind_acceptance = score_series(wind_conditions)
    temp_performance, temp_acceptance = score_series(temperature_conditions)
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex="col")
    for name in experiment.METHODS:
        style = "--" if name in {"OpenET", "Full"} else "-"
        axes[0, 0].plot(range(7), wind_performance[name], marker="o", ms=3.5,
                        lw=1.7, ls=style, color=COLORS[name], label=name)
        axes[1, 0].plot(range(7), wind_acceptance[name], marker="o", ms=3.5,
                        lw=1.7, ls=style, color=COLORS[name])
        axes[0, 1].plot(range(6), temp_performance[name], marker="o", ms=3.5,
                        lw=1.7, ls=style, color=COLORS[name])
        axes[1, 1].plot(range(6), temp_acceptance[name], marker="o", ms=3.5,
                        lw=1.7, ls=style, color=COLORS[name])
    axes[0, 0].set(title="A  Wind scale fault", ylabel="Station macro MAE (mm/day)")
    axes[1, 0].set(xlabel="Wind multiplier", ylabel="Accepted rows / station")
    axes[0, 1].set(title="B  Temperature fault", ylabel="Station macro MAE (mm/day)")
    axes[1, 1].set(xlabel="Temperature transformation", ylabel="Accepted rows / station")
    axes[0, 0].set_xticks(range(7), ["0", "0.447", "1", "2.237", "3.6", "5", "10"])
    axes[0, 1].set_xticks(range(6), ["Clean", "+5 C", "+10 C", "+20 C", "+32 C", "F as C"])
    axes[1, 0].set_ylim(-0.03, 1.03)
    axes[1, 1].set_ylim(-0.03, 1.03)
    for ax in axes.flat:
        ax.grid(axis="y", color="#D9D9D9", lw=0.6, alpha=0.55)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=6, bbox_to_anchor=(0.5, 0.005))
    save_figure(fig, "figure_9_tier1_dose_response", legend_space=0.19)


def secondary_fault_figure() -> None:
    conditions = ["clean", "vpd_x10", "wind_zero", "wind_dropout_median", "wind_stuck_7_days", "wind_doy_climatology"]
    labels = ["Clean", "VPD x10", "Wind zero", "Wind dropout", "Wind stuck 7 d", "Wind climatology"]
    performance, acceptance = score_series(conditions)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.7))
    x = np.arange(len(conditions))
    for name in experiment.METHODS:
        axes[0].plot(x, performance[name], marker="o", ms=3.5, lw=1.7,
                     color=COLORS[name], label=name)
        axes[1].plot(x, acceptance[name], marker="o", ms=3.5, lw=1.7,
                     color=COLORS[name])
    axes[0].set(ylabel="Station macro MAE (mm/day)", title="A  Fault performance")
    axes[1].set(ylabel="Accepted rows / station", title="B  Selector coverage")
    for ax in axes:
        ax.set_xticks(x, labels, rotation=20, ha="right")
        ax.grid(axis="y", color="#D9D9D9", lw=0.6, alpha=0.55)
    axes[1].set_ylim(-0.03, 1.03)
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="lower center", ncol=6, bbox_to_anchor=(0.5, 0.005))
    save_figure(fig, "figure_10_tier1_fault_types", legend_space=0.16)


def mechanism_figure() -> None:
    clean = read_predictions("clean")
    natural = read_predictions("manilacotton_clean")
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for ax, frame, title in [
        (axes[0, 0], clean, "A  Clean outer rows"),
        (axes[0, 1], natural, "B  Natural archive fault"),
    ]:
        points = ax.scatter(frame.predicted_gain, frame.realized_gain,
                            c=frame.abs_correction, s=15, alpha=0.42,
                            cmap="viridis", edgecolors="none")
        x_lower, x_upper = float(frame.predicted_gain.min()), float(frame.predicted_gain.max())
        y_lower, y_upper = float(frame.realized_gain.min()), float(frame.realized_gain.max())
        x_pad = 0.06 * max(x_upper - x_lower, 1e-6)
        y_pad = 0.06 * max(y_upper - y_lower, 1e-6)
        ax.set_xlim(x_lower - x_pad, x_upper + x_pad)
        ax.set_ylim(y_lower - y_pad, y_upper + y_pad)
        diagonal_start = max(x_lower - x_pad, y_lower - y_pad)
        diagonal_end = min(x_upper + x_pad, y_upper + y_pad)
        ax.plot([diagonal_start, diagonal_end], [diagonal_start, diagonal_end],
                color="#555555", lw=1, ls="--")
        ax.set(title=title, xlabel="Gain predicted improvement (mm/day)",
               ylabel="Realized absolute-error reduction (mm/day)")
        fig.colorbar(points, ax=ax, label="Absolute correction (mm/day)")
    for ax, frame, title in [
        (axes[1, 0], clean, "C  Clean correction inputs"),
        (axes[1, 1], natural, "D  Faulted correction inputs"),
    ]:
        points = ax.scatter(frame.abs_correction, frame.spread,
                            c=frame.predicted_gain, s=15, alpha=0.42,
                            cmap="coolwarm", edgecolors="none")
        ax.axvline(frame.train_abs_correction_q95.iloc[0], color="#222222", ls="--", lw=1)
        ax.axhline(frame.train_spread_q95.iloc[0], color="#222222", ls="--", lw=1)
        ax.set(title=title, xlabel="Absolute correction (mm/day)",
               ylabel="Ensemble spread (mm/day)")
        fig.colorbar(points, ax=ax, label="Gain predicted improvement (mm/day)")
    save_figure(fig, "figure_11_tier1_gain_mechanism")


def grouped_differences(frame: pd.DataFrame, baseline: str, method: str) -> tuple[np.ndarray, list[str]]:
    records = frame.assign(
        delta=np.abs(frame.y - frame[baseline]) - np.abs(frame.y - frame[method])
    ).groupby(["group", "station"], sort=True).delta.mean().reset_index()
    groups = records.groupby("group", sort=True).delta.sum()
    return groups.to_numpy(), groups.index.tolist()


def one_sided_signflip_p(values: np.ndarray, seed: int = 20260924) -> float:
    observed = float(values.sum())
    rng = np.random.default_rng(seed)
    signs = rng.integers(0, 2, size=(20000, len(values))) * 2 - 1
    null = signs @ values
    return float((np.count_nonzero(null >= observed) + 1) / (len(null) + 1))


def holm_adjust(pvalues: list[float]) -> list[float]:
    order = np.argsort(pvalues)
    adjusted = [0.0] * len(pvalues)
    current = 0.0
    for rank, index in enumerate(order):
        current = max(current, min(1.0, (len(pvalues) - rank) * pvalues[index]))
        adjusted[index] = current
    return adjusted


def primary_comparisons() -> None:
    comparisons = [
        ("LocalShrinkage", "SupportGain", "clean"),
        ("LocalShrinkage", "Uniform", "clean"),
        ("SupportGain", "Gain", "wind_x3.6"),
        ("SupportGain", "Gain", "wind_x5"),
        ("SupportGain", "Gain", "wind_x10"),
        ("SupportGain", "Gain", "temperature_fahrenheit_as_celsius"),
        ("SupportGain", "Gain", "vpd_x10"),
        ("AugmentedGain", "SupportGain", "wind_x5"),
        ("AugmentedGain", "SupportGain", "wind_x10"),
        ("AugmentedGain", "SupportGain", "temperature_fahrenheit_as_celsius"),
        ("AugmentedGain", "SupportGain", "vpd_x10"),
    ]
    rows = []
    for index, (method, baseline, condition) in enumerate(comparisons):
        frame = read_predictions(condition)
        interval = audit.bootstrap(frame, baseline, method)
        group_values, groups = grouped_differences(frame, baseline, method)
        rows.append({
            "condition": condition, "method": method, "baseline": baseline,
            "delta_macro_mae_favoring_method": interval["delta_macro_mae"],
            "ci95": interval["ci95"], "groups": len(groups),
            "one_sided_signflip_p": one_sided_signflip_p(group_values, 20260924 + index),
            "bootstrap_seed": 20260922, "bootstrap_draws": 2000,
        })
    adjusted = holm_adjust([row["one_sided_signflip_p"] for row in rows])
    for row, pvalue in zip(rows, adjusted):
        row["holm_p"] = pvalue
    (OUT / "primary_comparisons.json").write_text(json.dumps(rows, indent=2))


def main() -> None:
    receipt = json.loads((DATA / "receipt.json").read_text())
    if receipt["clean_cohort_sha256"] != sha(ROOT / "docs/results/ml_tier1/cohort_clean.csv"):
        raise RuntimeError("The clean cohort does not match the fitted results")
    FIG.mkdir(parents=True, exist_ok=True)
    trend_figure()
    secondary_fault_figure()
    mechanism_figure()
    primary_comparisons()
    (OUT / "analysis_receipt.json").write_text(json.dumps({
        "builder_sha256": sha(Path(__file__)),
        "model_receipt_sha256": sha(DATA / "receipt.json"),
        "figures4papers_reference": "scientific-figure-making design theory and API, accessed 2026-09-24",
        "methods": "Paired outer predictions, station-macro loss, 2,000 group bootstrap intervals, and Holm-adjusted one-sided group sign-flip tests.",
    }, indent=2))
    print("Tier 1 figures and paired summaries complete.")


if __name__ == "__main__":
    main()
