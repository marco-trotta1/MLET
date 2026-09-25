"""Build the Tier 3 risk-coverage figure."""
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
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/results/ml_tier3_gridmet_risk_coverage"
FIGURES = ROOT / "manuscript/arxiv/figures"
METHODS = [
    "Gain", "SupportGain", "MonoGain", "AugmentedGain", "TunedGain",
    "LogisticSign", "ConformalCSR",
]
COLORS = {
    "Gain": "#0F4D92",
    "SupportGain": "#42949E",
    "MonoGain": "#9A4D8E",
    "AugmentedGain": "#D28C45",
    "TunedGain": "#647C5B",
    "LogisticSign": "#B85555",
    "ConformalCSR": "#555555",
}
PANELS = [
    ("clean", "Clean weather inputs"),
    ("temperature_plus32", "Temperature input: +32 C"),
]

plt.rcParams.update(
    {
        "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 10,
        "axes.linewidth": 1.2,
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
    analysis_path = DATA / "analysis_receipt.json"
    curves_path = DATA / "risk_coverage_curves.csv"
    aurc_path = DATA / "aurc_summary.csv"
    for path in [analysis_path, curves_path, aurc_path]:
        if not path.is_file():
            raise RuntimeError("The risk-coverage analysis is incomplete")
    receipt = json.loads(analysis_path.read_text())
    if receipt["output_sha256"][curves_path.name] != sha256(curves_path):
        raise ValueError("Risk-coverage curves do not match their receipt")
    if receipt["output_sha256"][aurc_path.name] != sha256(aurc_path):
        raise ValueError("AURC summary does not match its receipt")
    curves = pd.read_csv(curves_path)
    aurc = pd.read_csv(aurc_path)

    figure, axes = plt.subplots(1, 2, figsize=(12.0, 4.8))
    for axis, (condition, title) in zip(axes, PANELS):
        subset = curves[curves.condition == condition]
        if set(subset.method.unique()) != set(METHODS):
            raise ValueError(f"The {condition} panel lacks a method")
        for method in METHODS:
            frame = subset[subset.method == method].sort_values("coverage")
            if len(frame) != 100:
                raise ValueError(f"The {condition} {method} curve needs 100 points")
            color = COLORS[method]
            axis.fill_between(
                frame.coverage.to_numpy(),
                frame.ci95_low_mm_day.to_numpy(),
                frame.ci95_high_mm_day.to_numpy(),
                color=color,
                alpha=0.09,
                linewidth=0,
            )
            if len(aurc[(aurc.condition == condition) & (aurc.method == method)]) != 1:
                raise ValueError(f"The {condition} {method} AURC is missing")
            axis.plot(
                frame.coverage,
                frame.selective_mae_mm_day,
                color=color,
                linewidth=1.7,
            )
        axis.set_title(title)
        axis.set_xlabel("Equal-station coverage")
        axis.set_xlim(0.01, 1.0)
        axis.grid(color="#D9D9D9", linewidth=0.6, alpha=0.65)
    axes[0].set_ylabel("Selective MAE among accepted corrections (mm/day)")
    axes[1].set_ylabel("Selective MAE among accepted corrections (mm/day)")
    handles = [
        Line2D([0], [0], color=COLORS[method], linewidth=1.8, label=method)
        for method in METHODS
    ]
    figure.legend(
        handles=handles,
        labels=METHODS,
        loc="lower center",
        ncol=4,
        bbox_to_anchor=(0.5, 0.0),
        columnspacing=1.7,
        handlelength=2.0,
    )
    figure.text(
        0.5,
        -0.035,
        "Shading: 95% spatial-group bootstrap intervals. Scores and fitted models stay fixed.",
        ha="center",
        va="top",
        fontsize=9,
        color="#555555",
    )
    figure.tight_layout(pad=1.3, rect=(0, 0.16, 1, 1))
    FIGURES.mkdir(parents=True, exist_ok=True)
    name = "figure_17_tier3_risk_coverage"
    pdf_path = FIGURES / f"{name}.pdf"
    png_path = FIGURES / f"{name}.png"
    figure.savefig(pdf_path, bbox_inches="tight")
    figure.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close(figure)

    output = {
        "analysis_receipt_sha256": sha256(analysis_path),
        "figure_script_sha256": sha256(Path(__file__)),
        "risk_coverage_curves_sha256": sha256(curves_path),
        "aurc_summary_sha256": sha256(aurc_path),
        "figures": {
            pdf_path.name: sha256(pdf_path),
            png_path.name: sha256(png_path),
        },
        "png_dpi": 300,
    }
    receipt_path = DATA / "figure_receipt.json"
    receipt_path.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    return output


if __name__ == "__main__":
    build()
