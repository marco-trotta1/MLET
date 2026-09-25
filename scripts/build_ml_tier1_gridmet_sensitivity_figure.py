"""Build the Tier 1 split and proximity sensitivity figure."""
# Figure layout and palette follow figures4papers scientific-figure-making.
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
DATA = ROOT / "docs/results/ml_tier1_gridmet_sensitivity"
FIGURES = ROOT / "manuscript/arxiv/figures"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_GRIDMET_SPLIT_PROXIMITY_PROTOCOL.md"
COLORS = {5: "#42949E", 10: "#0F4D92", 25: "#9A4D8E"}
GROUP_COUNTS = {5: 113, 10: 102, 25: 86}

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
    summary_path = DATA / "seed_summary.csv"
    contrast_path = DATA / "run_contrasts.csv"
    for path in [analysis_path, summary_path, contrast_path]:
        if not path.is_file():
            raise RuntimeError("The sensitivity analysis is incomplete")
    receipt = json.loads(analysis_path.read_text())
    if receipt["contrast_sha256"] != sha256(contrast_path):
        raise ValueError("The sensitivity contrasts do not match their receipt")
    if receipt["summary_sha256"] != sha256(summary_path):
        raise ValueError("The seed summary does not match its receipt")
    contrasts = pd.read_csv(contrast_path)
    clean = contrasts[contrasts.condition == "clean"]
    if clean.threshold_km.nunique() != 3 or clean.split_seed.nunique() != 10:
        raise ValueError("The clean sensitivity contrasts lack a declared arm")

    figure, axes = plt.subplots(1, 3, figsize=(11.2, 4.6), sharey=True)
    for axis, threshold in zip(axes, [5, 10, 25]):
        frame = clean[clean.threshold_km == threshold].sort_values("seed_index")
        if len(frame) != 10:
            raise ValueError(f"The {threshold} km panel needs ten split seeds")
        points = frame.support_improvement_mm_day.to_numpy()
        low = frame.ci95_low_mm_day.to_numpy()
        high = frame.ci95_high_mm_day.to_numpy()
        center = float(points.mean())
        spread = float(points.std(ddof=1))
        color = COLORS[threshold]
        positions = frame.seed_index.to_numpy() + 1

        axis.axhspan(center - spread, center + spread, color=color, alpha=0.12)
        axis.axhline(center, color=color, linewidth=1.5, alpha=0.9)
        axis.vlines(positions, low, high, color=color, linewidth=0.9)
        axis.hlines(low, positions - 0.09, positions + 0.09, color=color, linewidth=0.9)
        axis.hlines(high, positions - 0.09, positions + 0.09, color=color, linewidth=0.9)
        axis.plot(positions, points, marker="o", markersize=4, linestyle="none", color=color)
        axis.axhline(0, color="#777777", linewidth=0.9, linestyle="--")
        axis.set_title(f"{threshold} km ({GROUP_COUNTS[threshold]} groups)")
        axis.set_xlabel("Split seed index")
        axis.set_xticks(range(1, 11))
        axis.set_xlim(0.5, 10.5)
        axis.grid(axis="y", color="#D9D9D9", linewidth=0.6, alpha=0.55)

    axes[0].set_ylabel("SupportGain MAE improvement over Gain (mm/day)")
    figure.suptitle("Clean condition across split and proximity settings", y=1.02)
    figure.text(
        0.5,
        -0.03,
        "Whiskers: per-run 95% group-bootstrap intervals. Shading: mean ± 1 SD across ten seeds.",
        ha="center",
        va="top",
        fontsize=9,
        color="#555555",
    )
    figure.tight_layout(pad=1.3, rect=(0, 0.06, 1, 0.96))
    FIGURES.mkdir(parents=True, exist_ok=True)
    name = "figure_16_tier1_split_proximity_sensitivity"
    pdf_path = FIGURES / f"{name}.pdf"
    png_path = FIGURES / f"{name}.png"
    figure.savefig(pdf_path, bbox_inches="tight")
    figure.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close(figure)

    output = {
        "protocol_sha256": sha256(PROTOCOL),
        "analysis_receipt_sha256": sha256(analysis_path),
        "analysis_script_sha256": receipt["analysis_script_sha256"],
        "figure_script_sha256": sha256(Path(__file__)),
        "contrast_sha256": sha256(contrast_path),
        "figures": {
            pdf_path.name: sha256(pdf_path),
            png_path.name: sha256(png_path),
        },
        "png_dpi": 300,
    }
    (DATA / "figure_receipt.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    return output


if __name__ == "__main__":
    build()
