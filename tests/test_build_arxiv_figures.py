"""Tests for claim-safe arXiv figure generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_arxiv_figures


def _phase2_payload() -> dict[str, object]:
    """Return a compact Phase 2 result with all model arms."""
    names_and_mae = (
        ("B0_Persistence", 0.349, 1555),
        ("B1_CropCoefficient", 1.532, 7923),
        ("B2_WeatherRidge", 1.514, 7923),
        ("M1_OpenETDirect", 0.784, 7923),
        ("M2_OpenETRecal", 0.781, 7923),
        ("M3_OpenETRidge", 0.856, 7923),
    )
    return {
        "field_withheld": {
            "models": [
                {
                    "name": name,
                    "mae_mm": mae,
                    "rmse_mm": mae + 0.1,
                    "bias_mm": 0.0,
                    "sample_count": sample_count,
                }
                for name, mae, sample_count in names_and_mae
            ]
        },
        "h2": {
            "best_openet_free_model": "B2_WeatherRidge",
            "mae_delta_mm": 1.514 - 0.856,
            "mae_reduction_fraction": (1.514 - 0.856) / 1.514,
            "ci95_mm": [0.4, 0.9],
        },
    }


def test_phase2_figure_requires_m2_to_be_lowest_on_common_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The figure generator must not compare M2 with B0 or a mixed sample."""
    payload = _phase2_payload()
    models = payload["field_withheld"]["models"]
    assert isinstance(models, list)
    for model in models:
        assert isinstance(model, dict)
        if model["name"] == "B1_CropCoefficient":
            model["mae_mm"] = 0.2
    result_path = tmp_path / "phase2.json"
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(build_arxiv_figures, "PHASE2_RESULT", result_path)

    with pytest.raises(ValueError, match="common-sample|lowest MAE"):
        build_arxiv_figures._phase2_data()


def test_figure_labels_state_exact_scope() -> None:
    """Generated labels state the evaluation, grid, and interval scope."""
    assert build_arxiv_figures.PHASE2_LABEL == "station-held-out 10-fold evaluation"
    assert (
        build_arxiv_figures.GRID_LABEL
        == "common 0.5-degree GEFS grid-point subset"
    )
    assert (
        build_arxiv_figures.QUANTILE_BAND_LABEL
        == "uncalibrated ensemble p10 to p90 quantile band"
    )
    assert build_arxiv_figures.NOMINAL_COVERAGE_LABEL == "nominal coverage"
