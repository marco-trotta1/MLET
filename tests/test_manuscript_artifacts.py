"""Tests for deterministic manuscript-ready artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mlet.manuscript_artifacts import build_eto_hindcast_artifacts, build_phase2_artifacts


def _eto_result() -> dict[str, object]:
    """Return a complete, small-schema ETo result for generator tests."""
    metrics = []
    for lead_day in range(1, 21):
        metrics.append(_metric("lead_day", str(lead_day), lead_day))
    for season in ("DJF", "MAM", "JJA", "SON"):
        metrics.append(_metric("season", season, 21))
    for fold in range(5):
        metrics.append(_metric("spatial_fold", str(fold), 25))
    result = {
        "schema_version": 1,
        "kind": "idaho_eto_hindcast_result",
        "case_count": 400,
        "target_count": 12000,
        "station_count": 25,
        "evidence_sha256": hashlib.sha256(b"evidence").hexdigest(),
        "archive_sha256": hashlib.sha256(b"evidence").hexdigest(),
        "evaluation_sha256": "",
        "forecast_revisions": ["test-revision"],
        "target_sources": [
            {
                "uri": "https://www.usbr.gov/pn-bin/webarccsv.pl",
                "source_version": "agrimet-archive-v1",
            }
        ],
        "source_versions": [
            {
                "uri": "https://www.usbr.gov/pn-bin/webarccsv.pl",
                "source_version": "agrimet-archive-v1",
            }
        ],
        "exclusions": [],
        "support": {
            "minimum_paired_targets": 30,
            "cell_count": 400,
            "cells": [
                {
                    "lead_day": lead_day,
                    "season": season,
                    "spatial_fold": fold,
                    "sample_count": 120,
                    "minimum_required": 30,
                    "supported": True,
                }
                for lead_day in range(1, 21)
                for season in ("DJF", "MAM", "JJA", "SON")
                for fold in range(5)
            ],
        },
        "claim_safe_prose": {
            "scope": "MLET formally evaluates eto_mm only.",
            "completion": "The preregistered ETo evaluation is complete.",
            "skill": "Use skillful only when the paired 95% confidence interval for improvement over climatology excludes zero.",
            "promotion": "This result does not promote an operational forecast.",
        },
        "validation_scope": {
            "formal_hindcast_layers": ["eto_mm"],
            "nonforecast_analysis_layers": ["eta_analysis_mm"],
            "unvalidated_projection_layers": [
                "potential_et_c_mm",
                "eta_well_watered_mm",
                "eta_no_irrigation_mm",
            ],
        },
        "completion_blockers": [],
        "bootstrap": {
            "seed": 20260731,
            "replicates": 1000,
            "cluster_definition": "issue_date,target_id",
        },
        "metrics": metrics,
    }
    material = {
        "archive_sha256": result["archive_sha256"],
        "case_count": result["case_count"],
        "target_count": result["target_count"],
        "station_count": result["station_count"],
        "target_sources": result["target_sources"],
        "forecast_revisions": result["forecast_revisions"],
        "exclusions": result["exclusions"],
        "validation_scope": result["validation_scope"],
        "completion_blockers": result["completion_blockers"],
        "bootstrap": result["bootstrap"],
        "metrics": result["metrics"],
    }
    result["evaluation_sha256"] = hashlib.sha256(
        (json.dumps(material, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    return result


def _metric(group: str, key: str, index: int) -> dict[str, object]:
    return {
        "group": group,
        "key": key,
        "sample_count": 120,
        "mae_mm": 1.0 + index / 100.0,
        "rmse_mm": 1.2 + index / 100.0,
        "bias_mm": -0.1 + index / 1000.0,
        "p10_p90_coverage": 0.8,
        "mean_interval_width_mm": 2.0,
        "mean_pinball_loss_mm": 0.3,
        "baseline_mae_mm": 1.5,
        "mae_improvement_mm": 0.4,
        "mae_improvement_ci95_low_mm": 0.1,
        "mae_improvement_ci95_high_mm": 0.7,
        "bootstrap_cluster_count": 120,
    }


def test_phase2_artifact_generator_is_deterministic_and_claim_safe(
    tmp_path: Path,
) -> None:
    """Generated prose must retain provenance status and numeric results."""
    result = {
        "schema_version": 1,
        "kind": "mlet.phase2-openet-value-result",
        "evidence_status": "historical_report_reproduction_pending",
        "provenance": {
            "data_manifest_sha256": hashlib.sha256(b"manifest").hexdigest(),
            "git_revision": "historical-revision-unavailable",
            "seed": 20260713,
        },
        "field_withheld": {
            "models": [
                {"name": "B2_WeatherRidge", "mae_mm": 1.514, "rmse_mm": 2.687, "bias_mm": -0.098, "sample_count": 7923},
                {"name": "M3_OpenETRidge", "mae_mm": 0.856, "rmse_mm": 1.386, "bias_mm": -0.013, "sample_count": 7923},
            ]
        },
        "h2": {
            "best_openet_free_model": "B2_WeatherRidge",
            "mae_reduction_fraction": 0.434,
            "mae_delta_mm": 0.658,
            "ci95_mm": [0.399, 0.911],
        },
    }
    source = tmp_path / "phase2.json"
    source.write_text(json.dumps(result), encoding="utf-8")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    build_phase2_artifacts(source, first)
    build_phase2_artifacts(source, second)

    assert (first / "tables" / "phase2_model_comparison.csv").read_bytes() == (
        second / "tables" / "phase2_model_comparison.csv"
    ).read_bytes()
    assert (first / "figures" / "phase2_model_comparison.svg").read_bytes() == (
        second / "figures" / "phase2_model_comparison.svg"
    ).read_bytes()
    report = (first / "phase2_openet_value.md").read_text(encoding="utf-8")
    assert "Historical report; independent reproduction is pending." in report
    assert "0.658" in report


def test_eto_hindcast_artifact_generator_writes_required_tables_and_figures(
    tmp_path: Path,
) -> None:
    """Complete ETo results must generate deterministic manuscript inputs."""
    source = tmp_path / "eto.json"
    source.write_text(json.dumps(_eto_result()), encoding="utf-8")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    build_eto_hindcast_artifacts(source, first)
    build_eto_hindcast_artifacts(source, second)

    expected = (
        "tables/eto_skill_by_lead.csv",
        "tables/eto_skill_by_season.csv",
        "tables/eto_skill_by_spatial_fold.csv",
        "figures/eto_error_by_lead.svg",
        "figures/eto_coverage_by_lead.svg",
        "figures/eto_bias_by_season.svg",
        "idaho_eto_hindcast.md",
    )
    for relative in expected:
        assert (first / relative).read_bytes() == (second / relative).read_bytes()
    assert "weather-driven reference ETo" in (
        first / "idaho_eto_hindcast.md"
    ).read_text(encoding="utf-8")
