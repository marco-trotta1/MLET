"""Regression tests for the non-serving Idaho outlook residual experiment."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from mlet.cli import main
from mlet.experiments.idaho_outlook_residual import (
    FrozenSplit,
    ResidualMetric,
    _metric_blockers,
    evaluate_residual_evidence,
    write_residual_authority_request,
)
from mlet.outlook.residual_model import FEATURES, ResidualCase, fit_residual_model


ISSUE = "2024-01-01T00:00:00Z"


def _case(case_id: str, role: str, *, issue: str | None = None, block: str = "43:-117", target: float = 4.0) -> dict[str, object]:
    issue_by_role = {
        "train": "2023-03-01T00:00:00Z",
        "calibration": "2023-04-03T00:00:00Z",
        "test": "2024-01-01T00:00:00Z",
    }
    issue = issue or issue_by_role[role]
    valid = datetime.fromisoformat(issue.replace("Z", "+00:00")) + timedelta(days=1)
    season = "DJF" if valid.month in (12, 1, 2) else "MAM" if valid.month in (3, 4, 5) else "JJA" if valid.month in (6, 7, 8) else "SON"
    return {
        "case_id": case_id,
        "role": role,
        "layer": "eta_well_watered_mm",
        "target_kind": "declared_well_watered_scenario_target",
        "issue_time": issue,
        "valid_date": valid.date().isoformat(),
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
            "train_cutoff": "2023-03-01T00:00:00Z",
            "calibration_cutoff": "2023-04-03T00:00:00Z",
            "held_out_spatial_blocks": ["44:-116"],
            "held_out_seasons": ["DJF"],
        },
        "cases": [
            _case("train-1", "train", target=3.5),
            _case("train-2", "train", target=3.8),
            _case("calibration-1", "calibration", target=3.7),
            _case("test-1", "test", block="44:-116", target=3.7),
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
                season="DJF",
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


def test_underpowered_preregistered_strata_remain_named_with_blockers(tmp_path: Path) -> None:
    report, _receipt = evaluate_residual_evidence(_write(tmp_path / "underpowered.json", _evidence()))
    by_key = {(metric.group, metric.key): metric for metric in report.metrics}

    assert by_key[("lead_day", "20")].sample_count == 0
    assert by_key[("lead_day", "20")].physical_mae_mm is None
    assert by_key[("season", "DJF")].sample_count == 1
    assert "insufficient calibration support at lead 20: 0 < 5" in report.blockers
    assert "insufficient held-out test support in season DJF: 1 < 20" in report.blockers


def test_held_out_training_leakage_is_rejected(tmp_path: Path) -> None:
    evidence = _evidence()
    cases = evidence["cases"]
    assert isinstance(cases, list)
    first = cases[0]
    assert isinstance(first, dict)
    first["spatial_block"] = "44:-116"
    with pytest.raises(ValueError, match="held-out spatial block or season appears in training"):
        evaluate_residual_evidence(_write(tmp_path / "leaky.json", evidence))


def test_case_valid_date_and_caller_season_cannot_disagree_with_issue_and_lead() -> None:
    issue = datetime(2024, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="valid_date must equal"):
        ResidualCase(
            case_id="bad-date", role="train", layer="eta_well_watered_mm",
            target_kind="declared_well_watered_scenario_target", issue_time=issue,
            valid_date="2024-01-03", spatial_block="43:-117", season="DJF",
            feature_available_at=tuple((name, issue) for name in FEATURES),
            features=(1.0, 4.0, 0.5, 0.0, 0.8, 1.0, 120.0, 40.0, 5.0), physical_p50=3.0, target_mm=3.5,
        )
    with pytest.raises(ValueError, match="calendar season"):
        ResidualCase(
            case_id="bad-season", role="train", layer="eta_well_watered_mm",
            target_kind="declared_well_watered_scenario_target", issue_time=issue,
            valid_date="2024-01-02", spatial_block="43:-117", season="MAM",
            feature_available_at=tuple((name, issue) for name in FEATURES),
            features=(1.0, 4.0, 0.5, 0.0, 0.8, 1.0, 120.0, 40.0, 5.0), physical_p50=3.0, target_mm=3.5,
        )


def test_split_requires_preregistered_assignment_and_strict_cutoffs() -> None:
    with pytest.raises(ValueError, match="preregistered Idaho tile"):
        FrozenSplit(
            split_id="archive-decides-its-own-fold", train_cutoff=datetime(2023, 1, 1, tzinfo=timezone.utc),
            calibration_cutoff=datetime(2023, 2, 1, tzinfo=timezone.utc),
            held_out_spatial_blocks=("44:-116",), held_out_seasons=("DJF",),
        )
    with pytest.raises(ValueError, match="before calibration"):
        FrozenSplit(
            split_id="idaho-residual-v1-fold-4-djf", train_cutoff=datetime(2023, 2, 1, tzinfo=timezone.utc),
            calibration_cutoff=datetime(2023, 2, 1, tzinfo=timezone.utc),
            held_out_spatial_blocks=("44:-116",), held_out_seasons=("DJF",),
        )


def test_candidate_stays_false_when_local_report_and_policy_are_mutated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import mlet.experiments.idaho_outlook_residual as experiment

    evidence = _evidence()
    path = _write(tmp_path / "real.json", evidence)
    report, receipt = evaluate_residual_evidence(path)
    object.__setattr__(report, "blockers", ())
    monkeypatch.setattr(experiment, "_AUTHORITY_BLOCKER", "caller-cleared-authority-blocker")
    request_path = write_residual_authority_request(receipt, tmp_path / "request.json")
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    assert report.promotion is False
    assert payload["promotion"] is False
    assert "requires_independently_reconstructed_archive_authority" in payload["promotion_blockers"]
    assert payload["external_release_eligible"] is False


def test_lead_calibration_support_is_feasible_without_a_held_season_claim() -> None:
    split = FrozenSplit(
        split_id="idaho-residual-v1-fold-4-djf",
        train_cutoff=datetime(2023, 3, 1, tzinfo=timezone.utc),
        calibration_cutoff=datetime(2023, 4, 3, tzinfo=timezone.utc),
        held_out_spatial_blocks=("44:-116",), held_out_seasons=("DJF",),
    )

    def case(identifier: str, role: str, lead: int, issue: datetime, season: str) -> ResidualCase:
        valid = issue + timedelta(days=lead)
        return ResidualCase(
            case_id=identifier, role=role, layer="eta_well_watered_mm",
            target_kind="declared_well_watered_scenario_target", issue_time=issue,
            valid_date=valid.date().isoformat(), spatial_block="43:-117", season=season,
            feature_available_at=tuple((name, issue) for name in FEATURES),
            features=(float(lead), 4.0, 0.5, 0.0, 0.8, 1.0, 120.0, 40.0, 5.0),
            physical_p50=3.0, target_mm=3.5,
        )

    calibration = tuple(
        case(f"cal-{lead}-{replicate}", "calibration", lead, datetime(2023, 3, 1, tzinfo=timezone.utc), "MAM")
        for lead in range(1, 21) for replicate in range(5)
    )
    test = tuple(
        case(f"test-{lead}-{replicate}", "test", lead, datetime(2024, 1, 1, tzinfo=timezone.utc), "DJF")
        for lead in range(1, 21) for replicate in range(5)
    )
    metrics = tuple(
        ResidualMetric("lead_day", str(lead), 5, 1.0, 0.5, 0.8, 1.0)
        for lead in range(1, 21)
    ) + (ResidualMetric("season", "DJF", 100, 1.0, 0.5, 0.8, 1.0),)

    blockers = _metric_blockers(metrics, calibration, test, split)

    assert not [blocker for blocker in blockers if "insufficient" in blocker]
    assert "worst-season error degrades in DJF" not in blockers


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
    output = capsys.readouterr().out.lower()
    assert "promotion: false" in output
    assert "external_release_eligible: false" in output


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
