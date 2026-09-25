"""Draw the natural input violation comparison as a print-ready figure."""
# Figure layout and palette follow figures4papers scientific-figure-making.
# Source: https://github.com/ChenLiu-1996/figures4papers
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/results/ml_tier1_natural_violations"
FIGURES = ROOT / "manuscript/arxiv/figures"
STEM = "figure_19_tier1_natural_violations"
SUMMARY = OUT / "analysis_summary.json"
GROUPS = OUT / "group_effects_other.csv"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    summary = json.loads(SUMMARY.read_text())
    groups = pd.read_csv(GROUPS).sort_values("mean_station_delta_mm_day", ascending=False)
    population = summary["populations"]["other_invalid"]
    values = population["methods"]
    names = ("OpenET", "Full", "Gain", "SupportGain")
    colors = ("#767676", "#CFCECE", "#B64342", "#0F4D92")

    plt.rcParams.update({
        "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 12,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 1.5,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
    })
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 5.0), gridspec_kw={"width_ratios": [0.86, 1.14]})
    fig.patch.set_facecolor("white")

    left = axes[0]
    mae = [values[name]["station_macro_mae_mm_day"] for name in names]
    y = np.arange(len(names))
    left.barh(y, mae, color=colors, edgecolor="#272727", linewidth=0.7, height=0.63)
    left.set_yticks(y, names)
    left.invert_yaxis()
    left.set_xlim(0, 0.96)
    left.set_xlabel("Station-macro MAE (mm/day)")
    left.set_title("A  Error on 133 rows", loc="left", weight="bold", pad=11)
    left.tick_params(axis="y", length=0)
    for position, value in zip(y, mae, strict=True):
        left.text(value + 0.015, position, f"{value:.3f}", va="center", fontsize=10)

    right = axes[1]
    delta = groups.mean_station_delta_mm_day.to_numpy()
    position = np.arange(len(groups))
    right.axvline(0, color="#999999", linewidth=1.0, zorder=0)
    right.scatter(
        delta, position, s=30,
        color=np.where(delta > 1e-12, "#0F4D92", np.where(delta < -1e-12, "#B64342", "#999999")),
        edgecolors="#272727", linewidths=0.45, zorder=2,
    )
    right.set_yticks(position, groups.group.tolist(), fontsize=9)
    right.invert_yaxis()
    right.set_xlim(-0.012, 0.09)
    right.set_xlabel("Gain MAE minus SupportGain MAE (mm/day)")
    right.set_title("B  Group differences", loc="left", weight="bold", pad=11)
    right.tick_params(axis="y", length=0)
    for value, place in zip(delta, position, strict=True):
        if value > 1e-12:
            right.text(value + 0.003, place, f"{value:.3f}", va="center", fontsize=9)

    primary = summary["primary_comparison"]
    fig.text(
        0.5, 0.025,
        f"17 groups · 21 stations · paired group interval [{primary['ci95_mm_day'][0]:.3f}, "
        f"{primary['ci95_mm_day'][1]:.3f}] mm/day · fitted models fixed",
        ha="center", color="#5B5B5B", fontsize=10,
    )
    fig.tight_layout(rect=[0, 0.06, 1, 1], pad=1.35, w_pad=2.1)
    FIGURES.mkdir(parents=True, exist_ok=True)
    pdf = FIGURES / f"{STEM}.pdf"
    png = FIGURES / f"{STEM}.png"
    fig.savefig(pdf, facecolor="white")
    fig.savefig(png, dpi=300, facecolor="white")
    plt.close(fig)
    receipt = {
        "figure_script_sha256": sha256(Path(__file__)),
        "analysis_summary_sha256": sha256(SUMMARY),
        "group_effects_sha256": sha256(GROUPS),
        "pdf_sha256": sha256(pdf),
        "png_sha256": sha256(png),
        "source_workflow": "figures4papers scientific-figure-making",
    }
    (OUT / "figure_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Saved {pdf} and {png}")


if __name__ == "__main__":
    main()
