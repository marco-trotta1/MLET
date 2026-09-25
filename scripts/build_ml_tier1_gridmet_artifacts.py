"""Build figures from the fixed all-station Tier 1 results."""
# Figure layout and palette follow figures4papers scientific-figure-making.
# Source: https://github.com/ChenLiu-1996/figures4papers
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/results/ml_tier1_gridmet_10member"
FIGURES = ROOT / "manuscript/arxiv/figures"
COLORS = {
    "OpenET": "#4D4D4D",
    "Gain": "#E9A6A1",
    "SupportGain": "#0F4D92",
    "MonoGain": "#9A4D8E",
    "AugmentedGain": "#8BCF8B",
    "Uniform": "#42949E",
    "LocalShrinkage": "#3775BA",
}
METHODS = [
    "OpenET",
    "Gain",
    "SupportGain",
    "MonoGain",
    "AugmentedGain",
    "Uniform",
    "LocalShrinkage",
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


def rolling_origin(results: dict) -> None:
    years = sorted(int(year) for year in results["clean"]["test_years"])
    figure, (mae_axis, acceptance_axis) = plt.subplots(2, 1, figsize=(9.5, 7), sharex=True)
    for method in METHODS:
        metrics = [results["clean"]["test_years"][str(year)][method] for year in years]
        effects = np.array([metric["vs_openet"]["delta_macro_mae"] for metric in metrics])
        intervals = np.array([metric["vs_openet"]["ci95"] for metric in metrics])
        mae_axis.errorbar(
            years,
            effects,
            yerr=np.vstack([effects - intervals[:, 0], intervals[:, 1] - effects]),
            marker="o",
            markersize=3.5,
            linewidth=1.7,
            elinewidth=0.8,
            capsize=2,
            color=COLORS[method],
            label=method,
        )
        if method == "OpenET":
            accepted = [0.0] * len(years)
        else:
            accepted = [
                results["clean"]["test_years"][str(year)][method].get(
                    "station_macro_acceptance", 1.0
                )
                for year in years
            ]
        acceptance_axis.plot(
            years,
            accepted,
            marker="o",
            markersize=4,
            linewidth=1.7,
            color=COLORS[method],
        )
    mae_axis.axhline(0, color="#777777", linewidth=0.9, linestyle="--")
    mae_axis.set_ylabel("MAE reduction vs OpenET (mm/day)")
    mae_axis.set_title("Rolling-origin results with group-bootstrap intervals")
    acceptance_axis.set_ylabel("Station-macro acceptance")
    acceptance_axis.set_xlabel("Test year")
    acceptance_axis.set_ylim(-0.03, 1.03)
    handles, labels = mae_axis.get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.02))
    figure.tight_layout(pad=1.2, rect=(0, 0.09, 1, 1))
    name = "figure_14_tier1_gridmet_10member_rolling_origin"
    figure.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight")
    figure.savefig(FIGURES / f"{name}.png", dpi=300, bbox_inches="tight")
    plt.close(figure)


def wind_dose(results: dict) -> None:
    factors = [0, 0.447, 1, 2.237, 3.6, 5, 10]
    conditions = [f"wind_x{value:g}" for value in factors]
    points = np.arange(len(factors))
    figure, (mae_axis, acceptance_axis) = plt.subplots(2, 1, figsize=(9.5, 7), sharex=True)
    for method in METHODS:
        metrics = [results[condition]["pooled"][method] for condition in conditions]
        effects = np.array([metric["vs_openet"]["delta_macro_mae"] for metric in metrics])
        intervals = np.array([metric["vs_openet"]["ci95"] for metric in metrics])
        mae_axis.errorbar(
            points,
            effects,
            yerr=np.vstack([effects - intervals[:, 0], intervals[:, 1] - effects]),
            marker="o",
            markersize=3.5,
            linewidth=1.7,
            elinewidth=0.8,
            capsize=2,
            color=COLORS[method],
            label=method,
        )
        accepted = [
            results[condition]["pooled"][method].get("station_macro_acceptance", 1.0)
            for condition in conditions
        ]
        acceptance_axis.plot(
            points,
            accepted,
            marker="o",
            markersize=4,
            linewidth=1.7,
            color=COLORS[method],
        )
    mae_axis.axhline(0, color="#777777", linewidth=0.9, linestyle="--")
    mae_axis.set_ylabel("MAE reduction vs OpenET (mm/day)")
    mae_axis.set_title("GridMET wind dose response with group-bootstrap intervals")
    acceptance_axis.set_ylabel("Station-macro acceptance")
    acceptance_axis.set_xlabel("Wind multiplier")
    acceptance_axis.set_xticks(points, [f"{factor:g}" for factor in factors])
    acceptance_axis.set_ylim(-0.03, 1.03)
    handles, labels = mae_axis.get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.02))
    figure.tight_layout(pad=1.2, rect=(0, 0.09, 1, 1))
    name = "figure_15_tier1_gridmet_10member_wind_dose"
    figure.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight")
    figure.savefig(FIGURES / f"{name}.png", dpi=300, bbox_inches="tight")
    plt.close(figure)


def weather_fault_response(results: dict) -> None:
    fault_conditions = {
        "A  Wind scale fault": (
            "Wind multiplier",
            ["wind_x0", "wind_x0.447", "wind_x1", "wind_x2.237", "wind_x3.6", "wind_x5", "wind_x10"],
            ["0", "0.447", "1", "2.237", "3.6", "5", "10"],
        ),
        "B  Temperature fault": (
            "Temperature transform",
            ["clean", "temperature_plus5", "temperature_plus10", "temperature_plus20", "temperature_plus32", "temperature_fahrenheit_as_celsius"],
            ["Clean", "+5", "+10", "+20", "+32", "F as C"],
        ),
        "C  VPD unit fault": (
            "VPD condition",
            ["clean", "vpd_x10"],
            ["Clean", "x10"],
        ),
    }
    figure, axes = plt.subplots(
        2,
        3,
        figsize=(7.0, 4.8),
        sharex="col",
        gridspec_kw={"width_ratios": [1.2, 1.3, 0.85]},
    )
    for column, (title, (x_label, conditions, labels)) in enumerate(fault_conditions.items()):
        points = np.arange(len(conditions))
        mae_axis, acceptance_axis = axes[:, column]
        for method in METHODS:
            metrics = [results[condition]["pooled"][method] for condition in conditions]
            effects = np.array([metric["vs_openet"]["delta_macro_mae"] for metric in metrics])
            intervals = np.array([metric["vs_openet"]["ci95"] for metric in metrics])
            mae_axis.errorbar(
                points,
                effects,
                yerr=np.vstack([effects - intervals[:, 0], intervals[:, 1] - effects]),
                marker="o",
                markersize=3.5,
                linewidth=1.7,
                elinewidth=0.8,
                capsize=2,
                color=COLORS[method],
                label=method,
            )
            accepted = [metric.get("station_macro_acceptance", 0.0) for metric in metrics]
            acceptance_axis.plot(
                points,
                accepted,
                marker="o",
                markersize=3.5,
                linewidth=1.7,
                color=COLORS[method],
            )
        mae_axis.axhline(0, color="#777777", linewidth=0.9, linestyle="--")
        mae_axis.set_title(title)
        mae_axis.set_xticks(points, labels)
        mae_axis.tick_params(axis="x", labelbottom=False, labelsize=8)
        mae_axis.tick_params(axis="y", labelsize=8)
        mae_axis.grid(axis="y", color="#D9D9D9", linewidth=0.6, alpha=0.55)
        mae_axis.margins(y=0.12)
        acceptance_axis.set_xticks(points, labels)
        acceptance_axis.tick_params(axis="x", labelsize=8)
        acceptance_axis.tick_params(axis="y", labelsize=8)
        acceptance_axis.set_ylim(-0.03, 1.03)
        acceptance_axis.grid(axis="y", color="#D9D9D9", linewidth=0.6, alpha=0.55)
        acceptance_axis.set_xlabel(x_label)
    axes[0, 0].set_ylabel("MAE reduction vs OpenET\n(mm/day)")
    axes[1, 0].set_ylabel("Station-macro acceptance")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=4, fontsize=8.5, bbox_to_anchor=(0.5, -0.015))
    figure.tight_layout(pad=1.5, rect=(0, 0.1, 1, 1))
    name = "figure_20_tier1_gridmet_10member_weather_fault_response"
    figure.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight")
    figure.savefig(FIGURES / f"{name}.png", dpi=300, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    result_path = DATA / "results.json"
    if not result_path.exists():
        raise RuntimeError("The fixed all-station experiment is incomplete")
    FIGURES.mkdir(parents=True, exist_ok=True)
    results = json.loads(result_path.read_text())
    rolling_origin(results)
    wind_dose(results)
    weather_fault_response(results)
    print(
        json.dumps(
            {
                "figures": [
                    "figure_14_tier1_gridmet_10member_rolling_origin",
                    "figure_15_tier1_gridmet_10member_wind_dose",
                    "figure_20_tier1_gridmet_10member_weather_fault_response",
                ],
                "formats": ["PDF", "PNG"],
                "dpi": 300,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
