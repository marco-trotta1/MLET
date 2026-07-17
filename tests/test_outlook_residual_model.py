"""Regression tests for the non-serving Idaho outlook residual experiment."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from mlet.cli import main
from mlet.experiments.idaho_outlook_residual import (
    evaluate_residual_evidence,
    write_residual_authority_request,
)
from mlet.outlook.residual_model import FEATURES, ResidualCase, fit_residual_model


ISSUE = "2024-01-01T00:00:00Z"


def _case(case_id: str, role: str, *, issue: str = ISSUE, block: str = "43:-117", season: str = "MAM", target: float = 4.0) -> dict[str, object]:
    return {
        "case_id": case_id,
        "role": role,
        "layer": "eta_well_watered_mm",
        "target_kind": "declared_well_watered_scenario_target",
        "issue_time": issue,
        "valid_date": "2024-01-02",
        "spatial_block": block,
        "season": season,
        "feature_available_at": {name: issue for name in FEATURES},
        "features": {
            "lead_day": 1,
            "eto_p50": 4.0,
            "eto_spread": 0.5,
            "precip_p50": 0.0,
            "crop_fraction": 0.8,
            "kc": 1.0,
            "taw_mm": 120.0,
            "initial_depletion_mm": 40.0,
            "eta_analysis_age_days": 5.0,
        },
        "physical_p50": 3.0,
        "target_mm": target,
    }


def _evidence(*, classification: str = "software_fixture") -> dict[str, object]:
    return {
        "schema_version": 1,
        "evidence_classification": classification,
        "provenance": {
            "uri": "https://data.idaho.gov/archive/idaho-residual-v1",
            "version": "archive-v1",
            "sha256": "a" * 64,
            "available_at": ISSUE,
        },
        "hindcast_evidence": None,
        "split": {
            "split_id": "idaho-residual-v1-fold-4-djf",
            "train_cutoff": ISSUE,
            "calibration_cutoff": ISSUE,
            "held_out_spatial_blocks": ["44:-116"],
            "held_out_seasons": ["DJF"],
        },
        "cases": [
            _case("train-1", "train", target=3.5),
            _case("train-2", "train", target=3.8),
            _case("calibration-1", "calibration", target=3.7),
            _case("test-1", "test", block="44:-116", season="DJF", target=3.7),
        ],
    }


def _write(path: Path, value: dict[str, object]) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_residual_fit_receives_only_training_issue_times() -> None:
    issue = datetime(2024, 1, 1, tzinfo=timezone.utc)
    available = tuple((name, issue) for name in FEATURES)
    cases = tuple(
        ResidualCase(
            case_id=f"train-{index}",
            role="train",
            layer="eta_well_watered_mm",
            target_kind="declared_well_watered_scenario_target",
            issue_time=issue,
            valid_date="2024-01-02",
            spatial_block="43:-117",
            season="MAM",
            feature_available_at=available,
            features=(1.0, 4.0, 0.5, 0.0, 0.8, 1.0, 120.0, 40.0, 5.0),
            physical_p50=3.0,
            target_mm=3.5 + index / 10,
        )
        for index in range(2)
    )
    model = fit_residual_model(cases, cutoff=issue)
    assert max(model.training_issue_times) <= issue


def test_feature_after_issue_is_rejected(tmp_path: Path) -> None:
    evidence = _evidence()
    cases = evidence["cases"]
    assert isinstance(cases, list)
    first = cases[0]
    assert isinstance(first, dict)
    availability = first["feature_available_at"]
    assert isinstance(availability, dict)
    availability["eto_p50"] = "2024-01-01T01:00:00Z"
    with pytest.raises(ValueError, match="available after issue_time"):
        evaluate_residual_evidence(_write(tmp_path / "late.json", evidence))


def test_held_out_training_leakage_is_rejected(tmp_path: Path) -> None:
    evidence = _evidence()
    cases = evidence["cases"]
    assert isinstance(cases, list)
    first = cases[0]
    assert isinstance(first, dict)
    first["season"] = "DJF"
    with pytest.raises(ValueError, match="held-out spatial block or season appears in training"):
        evaluate_residual_evidence(_write(tmp_path / "leaky.json", evidence))


def test_candidate_is_false_even_when_metrics_are_eligible(tmp_path: Path) -> None:
    evidence = _evidence()
    path = _write(tmp_path / "real.json", evidence)
    report, receipt = evaluate_residual_evidence(path)
    object.__setattr__(report, "blockers", ())
    request_path = write_residual_authority_request(receipt, tmp_path / "request.json")
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    assert report.promotion is False
    assert payload["promotion"] is False
    assert "requires_separately_trusted_release_authority" in payload["promotion_blockers"]


def test_real_archived_cases_require_task8_hindcast_evidence(tmp_path: Path) -> None:
    evidence = _evidence(classification="real_archived")
    with pytest.raises(ValueError, match="requires hindcast_evidence"):
        evaluate_residual_evidence(_write(tmp_path / "unbound-real.json", evidence))


def test_fixture_is_non_scientific_and_cli_returns_candidate_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    evidence = _evidence(classification="software_fixture")
    path = _write(tmp_path / "fixture.json", evidence)
    report_path = tmp_path / "fixture.md"
    assert main(["evaluate-outlook-residual", "--cases", str(path), "--out", str(report_path)]) == 1
    assert "software fixture" in report_path.read_text(encoding="utf-8")
    assert "promotion: false" in capsys.readouterr().out.lower()


def test_cli_does_not_clobber_an_authority_request_destination(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path / "fixture.json", _evidence())
    report_path = tmp_path / "candidate.md"
    authority_path = tmp_path / "candidate.authority_request.json"
    authority_path.write_text("outside-process request", encoding="utf-8")
    assert main(["evaluate-outlook-residual", "--cases", str(path), "--out", str(report_path)]) == 2
    assert authority_path.read_text(encoding="utf-8") == "outside-process request"
    assert not report_path.exists()
    assert "destination already exists" in capsys.readouterr().err
