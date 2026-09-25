"""Refine the spatial holdout figure for paper readability."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/results/ml_tier1_spatial_holdout_sensitivity"
FIGURES = ROOT / "manuscript/arxiv/figures"
BLUE = "#0F4D92"
RED = "#B64342"
NEUTRAL = "#4D4D4D"
CONDITIONS = [
    "clean",
    "wind_x2.237",
    "wind_x3.6",
    "temperature_fahrenheit_as_celsius",
    "vpd_x10",
]
LABELS = ["Clean", "Wind x2.237", "Wind x3.6", "F as C", "VPD x10"]
STEM = "figure_23_tier1_spatial_holdout_sensitivity"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build() -> None:
    receipt_path = OUT / "analysis_receipt.json"
    results_path = OUT / "results.json"
    if not receipt_path.is_file() or not results_path.is_file():
        raise FileNotFoundError("The spatial holdout analysis is incomplete")
    receipt = json.loads(receipt_path.read_text())
    if receipt["results_sha256"] != sha256(results_path):
        raise ValueError("The analysis results do not match their receipt")
    pdf_path = FIGURES / f"{STEM}.pdf"
    png_path = FIGURES / f"{STEM}.png"
    old_figure = receipt["figure"]
    if old_figure["pdf_sha256"] != sha256(pdf_path):
        raise ValueError("The existing PDF figure does not match its receipt")
    if old_figure["png_sha256"] != sha256(png_path):
        raise ValueError("The existing PNG figure does not match its receipt")

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
    results = json.loads(results_path.read_text())["conditions"]
    positions = np.arange(len(CONDITIONS))
    effects = np.array(
        [results[name]["gain_minus_supportgain_mm_day"] for name in CONDITIONS]
    )
    intervals = np.array(
        [results[name]["simultaneous_ci95_mm_day"] for name in CONDITIONS]
    )
    errors = np.vstack([effects - intervals[:, 0], intervals[:, 1] - effects])
    gain_coverage = [
        100 * results[name]["gain_station_weighted_acceptance"]
        for name in CONDITIONS
    ]
    support_coverage = [
        100 * results[name]["supportgain_station_weighted_acceptance"]
        for name in CONDITIONS
    ]

    figure, axes = plt.subplots(
        2,
        1,
        figsize=(9.2, 5.7),
        sharex=True,
        gridspec_kw={"height_ratios": [1.25, 1]},
    )
    effect_axis, coverage_axis = axes
    effect_axis.errorbar(
        positions,
        effects,
        yerr=errors,
        fmt="o",
        color=BLUE,
        ecolor=NEUTRAL,
        elinewidth=1.6,
        capsize=4,
        markersize=6,
    )
    for position, value in zip(positions, effects):
        effect_axis.annotate(
            f"{value:+.3f}",
            (position, value),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
            color=BLUE,
        )
    effect_axis.axhline(0, color=NEUTRAL, linewidth=1.1)
    effect_axis.set_ylabel("Gain minus SupportGain MAE (mm/day)")
    effect_axis.set_title(
        "Five-fold spatial holdout: error and acceptance", loc="left"
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
        color=NEUTRAL,
    )
    coverage_axis.plot(
        positions,
        gain_coverage,
        marker="o",
        color=RED,
        linewidth=1.8,
        label="Gain",
    )
    coverage_axis.plot(
        positions,
        support_coverage,
        marker="o",
        color=BLUE,
        linewidth=1.8,
        label="SupportGain",
    )
    coverage_axis.set_ylabel("Station-weighted acceptance (%)")
    coverage_axis.set_ylim(0, 100)
    coverage_axis.set_xticks(positions, LABELS)
    coverage_axis.grid(axis="y", color="#E5E5E5", linewidth=0.8)
    coverage_axis.set_axisbelow(True)
    coverage_axis.legend(loc="lower left", ncol=2)
    figure.tight_layout(pad=1.2)
    figure.savefig(pdf_path, bbox_inches="tight", facecolor="white")
    figure.savefig(png_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(figure)

    refined = {
        "reference": (
            "https://github.com/ChenLiu-1996/figures4papers/"
            "blob/main/scientific-figure-making/SKILL.md"
        ),
        "design": (
            "Uses the repository palette, sans-serif fallback, minimal spines, "
            "short labels, direct estimates, and vector PDF export."
        ),
        "pdf_sha256": sha256(pdf_path),
        "png_sha256": sha256(png_path),
        "builder_sha256": sha256(Path(__file__)),
    }
    (OUT / "figure_receipt.json").write_text(
        json.dumps(refined, indent=2) + "\n"
    )
    receipt["figure"] = refined
    receipt["figure_builder_sha256"] = refined["builder_sha256"]
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print("Figure 23 refinement complete.", flush=True)


if __name__ == "__main__":
    build()
