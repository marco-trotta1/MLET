"""Tests for claim-safe arXiv figure generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mlet.outlook.eto_hindcast import evaluate_eto_hindcast_evidence
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
        "station_count": 85,
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
    assert (
        build_arxiv_figures.EMPIRICAL_COVERAGE_LABEL
        == "empirical p10 to p90 coverage"
    )
    assert (
        build_arxiv_figures.NOMINAL_COVERAGE_LABEL
        == "nominal p10 to p90 coverage target"
    )
    assert build_arxiv_figures.NOMINAL_COVERAGE_TARGET == 0.80


def test_coverage_values_separate_empirical_and_nominal() -> None:
    """Coverage fields preserve the evaluated value and frozen target."""
    report = evaluate_eto_hindcast_evidence(build_arxiv_figures.FEASIBILITY_EVIDENCE)
    metric = next(item for item in report.metrics if item.group == "season" and item.key == "JJA")

    values = build_arxiv_figures._coverage_values(metric)

    assert values == {"empirical": 0.25, "nominal": 0.80}


def test_phase2_render_uses_controlled_h2_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 2 rendering must resolve every annotation value at runtime."""
    result_path = tmp_path / "phase2.json"
    result_path.write_text(json.dumps(_phase2_payload()), encoding="utf-8")
    output_dir = tmp_path / "figures"
    output_dir.mkdir()
    monkeypatch.setattr(build_arxiv_figures, "PHASE2_RESULT", result_path)

    build_arxiv_figures._configure_plot_style()
    build_arxiv_figures._figure_phase2_models(output_dir)

    for suffix in ("pdf", "png"):
        output = output_dir / f"figure_2_phase2_models.{suffix}"
        assert output.is_file()
        assert output.stat().st_size > 0


def test_feasibility_paths_follow_the_single_evidence_case() -> None:
    """Figure inputs must resolve from the tracked one-case evidence record."""
    case_id, outlook_path, target_path = (
        build_arxiv_figures._resolve_feasibility_case_paths()
    )

    assert case_id == "issue-20190703-station-BOII-season-JJA-fold-2"
    assert outlook_path.name == "outlook.json"
    assert target_path.name == "target.json"
    assert "season-JJA-fold-2" in outlook_path.parent.name
    assert "season-JJA-fold-2" in target_path.parent.name


def test_support_annotation_comes_from_evaluated_metrics() -> None:
    """The support note must report the evaluated season, fold, and count."""
    report = evaluate_eto_hindcast_evidence(build_arxiv_figures.FEASIBILITY_EVIDENCE)

    annotation = build_arxiv_figures._support_tensor_annotation(report)

    assert "JJA-fold-2" in annotation
    assert "20 cell observations" in annotation
    assert "fold-4" not in annotation


def test_feasibility_paths_reject_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evidence paths must stay below the configured archive root."""
    root = tmp_path / "archive"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    evidence = root / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "case",
                        "forecast": {"artifact_path": "../outside.json"},
                        "target": {"path": "target.json"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "target.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(build_arxiv_figures, "FEASIBILITY_ROOT", root)
    monkeypatch.setattr(build_arxiv_figures, "FEASIBILITY_EVIDENCE", evidence)

    with pytest.raises(ValueError, match="outside|relative"):
        build_arxiv_figures._resolve_feasibility_case_paths()
