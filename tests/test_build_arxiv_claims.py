"""Tests for scope checks in the arXiv claim generator."""

from __future__ import annotations

import pytest

from scripts import build_arxiv_claims


def _phase2_payload() -> dict[str, object]:
    """Return a compact Phase 2 result with the required model records."""
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


def test_m2_scope_check_excludes_b0_and_requires_the_common_sample() -> None:
    """The descriptive M2 claim must cover only the five common-sample models."""
    payload = _phase2_payload()
    models = payload["field_withheld"]["models"]
    assert isinstance(models, list)
    for model in models:
        assert isinstance(model, dict)
        if model["name"] == "B1_CropCoefficient":
            model["mae_mm"] = 0.2
    with pytest.raises(ValueError, match="common-sample|lowest MAE"):
        build_arxiv_claims._validate_phase2_models(
            build_arxiv_claims._model_by_name(payload)
        )


def test_claim_labels_keep_b0_and_h2_roles_distinct() -> None:
    """Claim labels identify B0 as a diagnostic and H2 as a comparison."""
    models = build_arxiv_claims._model_by_name(_phase2_payload())
    build_arxiv_claims._validate_phase2_models(models)
    assert build_arxiv_claims._b0_scope_label(models) == (
        "B0: 1,555 consecutive-day pairs"
    )
    assert build_arxiv_claims.H2_SCOPE_LABEL == "H2: preregistered comparison"


def test_b0_scope_label_reads_the_machine_sample_count() -> None:
    """The generated B0 label must follow the validated record count."""
    models = build_arxiv_claims._model_by_name(_phase2_payload())
    models["B0_Persistence"]["sample_count"] = 1_556
    assert build_arxiv_claims._b0_scope_label(models) == (
        "B0: 1,556 consecutive-day pairs"
    )


def test_phase2_station_count_claim_reads_the_result_record() -> None:
    """The generated station claim must follow the serialized result count."""
    payload = _phase2_payload()
    payload["station_count"] = 84
    assert build_arxiv_claims._phase2_station_count(payload) == 84


def test_claims_separate_empirical_and_nominal_coverage() -> None:
    """Generated claim macros must keep measured and nominal coverage distinct."""
    macros = {
        line.split("}", 1)[0].split("\\")[-1]: line
        for line in build_arxiv_claims._build_claims()
        if "Coverage" in line
    }

    assert "FeasibilityEmpiricalCoverage" in macros
    assert "0.25" in macros["FeasibilityEmpiricalCoverage"]
    assert "FeasibilityNominalCoverage" in macros
    assert "0.80" in macros["FeasibilityNominalCoverage"]
    assert "nominal" not in macros["FeasibilityEmpiricalCoverage"].casefold()
