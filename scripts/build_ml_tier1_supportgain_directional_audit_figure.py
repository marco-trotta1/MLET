"""Draw the exploratory SupportGain directional audit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/results/ml_tier1_supportgain_directional_audit"
FIGURES = ROOT / "manuscript/arxiv/figures"
COMPARISONS = OUT / "two_sided_comparisons.json"
ANALYSIS_RECEIPT = OUT / "two_sided_analysis_receipt.json"
STEM = "figure_21_tier1_supportgain_directional_audit"

LABELS = {
    "clean": "Clean",
    "wind_x0": "Wind ×0",
    "wind_x0.447": "Wind ×0.447",
    "wind_x2.237": "Wind ×2.237",
    "wind_x3.6": "Wind ×3.6",
    "wind_x5": "Wind ×5",
    "wind_x10": "Wind ×10",
    "temperature_plus5": "Temperature +5 °C",
    "temperature_plus10": "Temperature +10 °C",
    "temperature_plus20": "Temperature +20 °C",
    "temperature_plus32": "Temperature +32 °C",
    "temperature_fahrenheit_as_celsius": "Fahrenheit read as Celsius",
    "vpd_x10": "VPD ×10",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    receipt = json.loads(ANALYSIS_RECEIPT.read_text())
    if sha256(COMPARISONS) != receipt["comparisons_sha256"]:
        raise ValueError("The comparison data do not match the analysis receipt")
    rows = json.loads(COMPARISONS.read_text())
    if len(rows) != 39:
        raise ValueError("The directional audit must contain 39 comparisons")

    colors = {"significant": "#0F4D92", "other": "#767676"}
    plt.rcParams.update({
        "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 1.1,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })

    figure = plt.figure(figsize=(9.1, 5.5), facecolor="white")
    outer = figure.add_gridspec(1, 2, width_ratios=[0.78, 1.72], wspace=0.37)
    count_axis = figure.add_subplot(outer[0, 0])
    plot_grid = outer[0, 1].subgridspec(2, 1, height_ratios=[9.1, 1.7], hspace=0.33)
    effect_axis = figure.add_subplot(plot_grid[0, 0])
    vpd_axis = figure.add_subplot(plot_grid[1, 0])

    baselines = ["Gain", "MonoGain", "AugmentedGain"]
    significant_counts = [
        sum(row["baseline"] == name and row["two_sided_holm_p"] < 0.05 for row in rows)
        for name in baselines
    ]
    y_count = np.arange(len(baselines))
    count_axis.barh(
        y_count,
        significant_counts,
        color=[colors["significant"], colors["significant"], colors["other"]],
        edgecolor="#272727",
        linewidth=0.5,
        height=0.56,
    )
    count_axis.set_yticks(y_count, baselines)
    count_axis.invert_yaxis()
    count_axis.set_xlim(0, 13.2)
    count_axis.set_xticks([0, 4, 8, 12])
    count_axis.set_xlabel("Holm-significant conditions")
    count_axis.set_title("A  Count by baseline", loc="left", weight="bold", pad=10)
    count_axis.tick_params(axis="y", length=0)
    for position, value in zip(y_count, significant_counts, strict=True):
        count_axis.text(value + 0.25, position, f"{value}/13", va="center", fontsize=9)

    gain_rows = [row for row in rows if row["baseline"] == "Gain"]
    visible = [row for row in gain_rows if row["condition"] != "vpd_x10"]
    positions = np.arange(len(visible))
    for position, row in zip(positions, visible, strict=True):
        estimate = row["delta_macro_mae_favoring_supportgain"]
        low, high = row["ci95"]
        color = colors["significant"] if row["two_sided_holm_p"] < 0.05 else colors["other"]
        effect_axis.errorbar(
            estimate,
            position,
            xerr=[[estimate - low], [high - estimate]],
            fmt="o",
            color=color,
            ecolor=color,
            markersize=4.6,
            capsize=2.2,
            linewidth=1.2,
            markeredgecolor="#272727",
            markeredgewidth=0.35,
        )
    effect_axis.axvline(0, color="#B64342", linewidth=1, zorder=0)
    effect_axis.set_yticks(positions, [LABELS[row["condition"]] for row in visible])
    effect_axis.invert_yaxis()
    effect_axis.set_xlim(-0.08, 1.12)
    effect_axis.set_xticks([0, 0.25, 0.50, 0.75, 1.00])
    effect_axis.set_xlabel("Gain MAE − SupportGain MAE (mm/day)")
    effect_axis.set_title("B  Paired differences versus Gain", loc="left", weight="bold", pad=10)
    effect_axis.tick_params(axis="y", length=0, labelsize=8)
    effect_axis.grid(axis="x", color="#E4E4E4", linewidth=0.6, zorder=0)

    vpd = next(row for row in gain_rows if row["condition"] == "vpd_x10")
    estimate = vpd["delta_macro_mae_favoring_supportgain"]
    low, high = vpd["ci95"]
    vpd_color = colors["significant"] if vpd["two_sided_holm_p"] < 0.05 else colors["other"]
    vpd_axis.errorbar(
        estimate,
        0,
        xerr=[[estimate - low], [high - estimate]],
        fmt="o",
        color=vpd_color,
        ecolor=vpd_color,
        markersize=4.6,
        capsize=2.2,
        linewidth=1.2,
        markeredgecolor="#272727",
        markeredgewidth=0.35,
    )
    vpd_axis.set_xlim(1.9, 3.9)
    vpd_axis.set_xticks([2.0, 2.5, 3.0, 3.5])
    vpd_axis.set_yticks([])
    vpd_axis.set_xlabel("VPD ×10 versus Gain (mm/day), separate scale", labelpad=2)
    vpd_axis.grid(axis="x", color="#E4E4E4", linewidth=0.6, zorder=0)
    vpd_axis.text(
        0.01,
        0.66,
        f"+{estimate:.2f} [{low:.2f}, {high:.2f}]",
        transform=vpd_axis.transAxes,
        ha="left",
        va="center",
        fontsize=8,
        color="#171717",
    )

    figure.text(
        0.5,
        0.025,
        "Two-sided Holm: blue p < 0.05, gray p ≥ 0.05 · Outcome review preceded analysis · 7,842 rows · 101 stations · 64 groups",
        ha="center",
        color="#5B5B5B",
        fontsize=8.5,
    )
    figure.subplots_adjust(left=0.155, right=0.985, top=0.91, bottom=0.13)

    FIGURES.mkdir(parents=True, exist_ok=True)
    pdf = FIGURES / f"{STEM}.pdf"
    png = FIGURES / f"{STEM}.png"
    figure.savefig(pdf, facecolor="white", bbox_inches="tight")
    figure.savefig(png, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(figure)
    figure_receipt = {
        "figure_script_sha256": sha256(Path(__file__)),
        "analysis_receipt_sha256": sha256(ANALYSIS_RECEIPT),
        "comparisons_sha256": sha256(COMPARISONS),
        "pdf_sha256": sha256(pdf),
        "png_sha256": sha256(png),
        "source_workflow": "figures4papers scientific-figure-making",
    }
    (OUT / "figure_receipt.json").write_text(json.dumps(figure_receipt, indent=2) + "\n")
    print(f"Saved {pdf} and {png}")


if __name__ == "__main__":
    main()
