"""Build the cropland-only training sensitivity figure."""
# Layout and palette adapt figures4papers scientific-figure-making.
# Source: https://github.com/ChenLiu-1996/figures4papers
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/results/ml_tier1_cropland"
FIGURES = ROOT / "manuscript/arxiv/figures"
BLUE = "#0F4D92"
GREEN = "#8BCF8B"
RED = "#B64342"

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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build() -> dict:
    receipt_path = DATA / "analysis_receipt.json"
    summary_path = DATA / "performance_summary.csv"
    primary_path = DATA / "primary_comparison.json"
    for path in [receipt_path, summary_path, primary_path]:
        if not path.is_file():
            raise RuntimeError("The cropland analysis is incomplete")
    receipt = json.loads(receipt_path.read_text())
    if receipt["performance_summary_sha256"] != sha256(summary_path):
        raise ValueError("The cropland summary does not match its receipt")
    if receipt["primary_comparison_sha256"] != sha256(primary_path):
        raise ValueError("The primary comparison does not match its receipt")
    summary = pd.read_csv(summary_path)
    annual = summary[summary.period != "all_test_years"].pivot(
        index="period", columns="system", values="station_macro_mae_mm_day"
    )
    counts = summary[summary.period != "all_test_years"].drop_duplicates("period").set_index("period")
    annual["improvement"] = (
        annual.AllStationSupportGain - annual.CroplandOnlySupportGain
    )
    annual["groups"] = counts["groups"]
    annual = annual.loc[sorted(annual.index, key=int)]
    primary = json.loads(primary_path.read_text())

    figure, axis = plt.subplots(figsize=(7.2, 4.2))
    values = annual.improvement.to_numpy()
    colors = [GREEN if value >= 0 else RED for value in values]
    positions = list(range(len(annual)))
    axis.bar(positions, values, color=colors, width=0.66, edgecolor="white", linewidth=0.8)
    axis.axhline(0, color="#4D4D4D", linewidth=1.3)
    for position, value in zip(positions, values):
        offset = 0.004 if value >= 0 else -0.004
        axis.text(
            position,
            value + offset,
            f"{value:+.3f}",
            ha="center",
            va="bottom" if value >= 0 else "top",
            fontsize=9,
            color="#444444",
        )
    pooled_position = len(annual) + 0.8
    pooled_value = float(primary["difference_mm_day"])
    interval = primary["ci95_mm_day"]
    axis.errorbar(
        pooled_position,
        pooled_value,
        yerr=[[pooled_value - interval[0]], [interval[1] - pooled_value]],
        fmt="o",
        color=BLUE,
        markersize=6,
        linewidth=1.8,
        capsize=4,
        zorder=3,
    )
    axis.text(
        pooled_position,
        pooled_value + 0.006,
        f"{pooled_value:+.3f}",
        ha="center",
        va="bottom",
        fontsize=9,
        color=BLUE,
    )
    axis.set_xticks(
        positions + [pooled_position],
        [
            f"{year}\ng={int(groups)}"
            for year, groups in zip(annual.index, annual["groups"])
        ] + [f"Pooled\ng={primary['groups']}"],
    )
    axis.tick_params(axis="x", labelsize=9)
    axis.tick_params(axis="y", labelsize=10)
    axis.set_xlim(-0.6, pooled_position + 0.6)
    axis.set_ylabel("All-station minus crop-only MAE (mm/day)", fontsize=11)
    axis.set_title("Cropland-only vs all-station SupportGain", fontsize=12)
    axis.set_ylim(
        min(-0.06, float(values.min()) - 0.02),
        max(float(values.max()), float(interval[1])) + 0.025,
    )
    axis.grid(axis="y", color="#D9D9D9", linewidth=0.8, alpha=0.65)
    axis.set_axisbelow(True)
    figure.text(
        0.5,
        -0.015,
        "Bars show yearly estimates. Tick labels give group counts (g). The pooled point and whisker show the 95% spatial-group interval. "
        "Positive values favor cropland-only training.",
        ha="center",
        va="top",
        fontsize=9.5,
        color="#555555",
    )
    figure.tight_layout(pad=1.8, rect=(0, 0.08, 1, 1))
    FIGURES.mkdir(parents=True, exist_ok=True)
    name = "figure_18_tier1_cropland_training"
    pdf_path = FIGURES / f"{name}.pdf"
    png_path = FIGURES / f"{name}.png"
    figure.savefig(pdf_path, bbox_inches="tight")
    figure.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close(figure)
    output = {
        "analysis_receipt_sha256": sha256(receipt_path),
        "figure_script_sha256": sha256(Path(__file__)),
        "performance_summary_sha256": sha256(summary_path),
        "primary_comparison_sha256": sha256(primary_path),
        "figures": {
            pdf_path.name: sha256(pdf_path),
            png_path.name: sha256(png_path),
        },
        "png_dpi": 300,
    }
    figure_receipt = DATA / "figure_receipt.json"
    figure_receipt.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    return output


if __name__ == "__main__":
    build()
