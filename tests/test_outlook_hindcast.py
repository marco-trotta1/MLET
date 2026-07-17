"""Regression tests for the preregistered outlook hindcast release gate."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from mlet.outlook.hindcast import (
    AvailableRecord,
    evaluate_hindcast_evidence,
    HindcastCase,
    HindcastRow,
    load_hindcast_cases,
    render_hindcast_markdown,
    run_hindcast,
    select_inputs_as_of,
    write_hindcast_validation,
)
from mlet.outlook.manifest import build_manifest
from mlet.cli import _trusted_hindcast_output, main


ISSUE_TIME = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _record(*, available_at: datetime = ISSUE_TIME) -> AvailableRecord:
    return AvailableRecord(
        name="archived-gefs",
        available_at=available_at,
        source_version="gefs-v1",
        sha256="a" * 64,
        uri="https://example.test/gefs",
    )


def _row(*, layer: str, lead_day: int) -> HindcastRow:
    valid_date = ISSUE_TIME.date() + timedelta(days=lead_day)
    target_kind = {
        "eto_mm": "independent_asce_short_reference_eto",
        "eta_well_watered_mm": "declared_well_watered_scenario_target",
        "eta_no_irrigation_mm": "declared_no_irrigation_scenario_target",
    }[layer]
    return HindcastRow(
        layer=layer,
        lead_day=lead_day,
        valid_date=valid_date,
        spatial_block="43:-117",
        p10=3.0,
        p50=4.0,
        p90=5.0,
        target_mm=4.5,
        target_kind=target_kind,
        target_available_at=ISSUE_TIME + timedelta(days=lead_day + 2),
    )


def _complete_case() -> HindcastCase:
    return HindcastCase(
        issue_time=ISSUE_TIME,
        records=(_record(),),
        rows=tuple(
            _row(layer=layer, lead_day=lead_day)
            for layer in (
                "eto_mm",
                "eta_well_watered_mm",
                "eta_no_irrigation_mm",
            )
            for lead_day in range(1, 21)
        ),
    )


def _write_verified_evidence(tmp_path: Path, *, classification: str = "real_archived") -> Path:
    """Create an archived byte bundle; values are never inline in the case file."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"archived source")
    issue = ISSUE_TIME.strftime("%Y-%m-%dT%H:%M:%SZ")
    collections = []
    target_values = []
    for lead in range(1, 21):
        valid = (ISSUE_TIME.date() + timedelta(days=lead)).isoformat()
        layers = {}
        for layer, kind in {
            "eto_mm": "independent_asce_short_reference_eto",
            "eta_well_watered_mm": "declared_well_watered_scenario_target",
            "eta_no_irrigation_mm": "declared_no_irrigation_scenario_target",
        }.items():
            layers[layer] = {"p10": 3.0, "p50": 4.0, "p90": 5.0}
            target_values.append({"layer": layer, "lead_day": lead, "valid_date": valid, "grid_id": "43:-117", "target_mm": 4.5, "target_kind": kind})
        collections.append({"lead_day": lead, "features": [{"properties": {"grid_id": "43:-117", "layers": layers}}]})
    forecast = tmp_path / "outlook.json"
    forecast.write_text(json.dumps({"run_id": "PLACEHOLDER", "issued_at": issue, "fixture_non_scientific": False, "feature_collections": collections}), encoding="utf-8")
    manifest = build_manifest(issue, {"weather": source}, "test-revision", issue)
    # The output has to carry the manifest identity, then the manifest pins its exact bytes.
    forecast.write_text(json.dumps({"run_id": manifest.run_id, "issued_at": issue, "fixture_non_scientific": False, "feature_collections": collections}), encoding="utf-8")
    manifest = manifest.with_artifact_sha256({"outlook.json": hashlib.sha256(forecast.read_bytes()).hexdigest()})
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    target = tmp_path / "targets.json"
    target.write_text(json.dumps({"schema_version": 1, "kind": "idaho_outlook_hindcast_target", "receipt": {"uri": "https://archive.example.org/targets", "source_version": "target-v1", "available_at": "2026-07-23T00:00:00Z"}, "values": target_values}), encoding="utf-8")
    receipt = {"name": "weather", "available_at": issue, "source_version": "archive-v1", "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "uri": source.resolve().as_uri()}
    assumptions = {name: {**receipt, "name": name} for name in ("water", "crop", "precip", "soil")}
    evidence = {
        "schema_version": 2,
        "evidence_classification": classification,
        "provenance": {"uri": "https://archive.example.org/idaho", "version": "archive-v1", "sha256": "b" * 64, "available_at": issue},
        "cases": [{
            "issue_time": issue,
            "forecast": {"run_id": manifest.run_id, "manifest_path": "manifest.json", "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "artifact_path": "outlook.json", "artifact_sha256": hashlib.sha256(forecast.read_bytes()).hexdigest()},
            "target": {"path": "targets.json", "uri": "https://archive.example.org/targets", "source_version": "target-v1", "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "available_at": "2026-07-23T00:00:00Z"},
            "source_receipts": [receipt],
            "holdout": {"spatial_block": "43:-117", "fold": 1, "held_out_fold": 1, "training_folds": [0, 2, 3, 4], "held_out_season": "JJA", "training_seasons": ["DJF", "MAM", "SON"], "training_cutoff": issue, "calibration_cutoff": issue},
            "scenario_assumptions": assumptions,
        }],
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    return evidence_path


def test_select_inputs_as_of_excludes_future_records() -> None:
    future = _record(available_at=ISSUE_TIME + timedelta(seconds=1))

    selected = select_inputs_as_of((_record(), future), issue_time=ISSUE_TIME)

    assert selected == [_record()]


def test_available_record_requires_a_strict_utc_timestamp() -> None:
    with pytest.raises(ValueError, match="strict UTC"):
        AvailableRecord(
            name="bad",
            available_at=datetime(2026, 7, 1),
            source_version="v1",
            sha256="a" * 64,
            uri="https://example.test/bad",
        )


def test_available_record_rejects_ambiguous_source_metadata() -> None:
    with pytest.raises(ValueError, match="source uri"):
        AvailableRecord(
            name="bad",
            available_at=ISSUE_TIME,
            source_version="v1",
            sha256="a" * 64,
            uri=None,  # type: ignore[arg-type]
        )


def test_hindcast_reports_lead_metrics_and_interval_coverage() -> None:
    report = run_hindcast((_complete_case(),))

    eto_lead_one = next(
        metric
        for metric in report.metrics
        if metric.layer == "eto_mm" and metric.group == "lead_day" and metric.key == "1"
    )
    assert eto_lead_one.sample_count == 1
    assert eto_lead_one.mae_mm == pytest.approx(0.5)
    assert eto_lead_one.p10_p90_coverage == pytest.approx(1.0)
    assert {metric.group for metric in report.metrics} == {
        "lead_day",
        "month",
        "season",
        "spatial_block",
    }
    assert report.input_audit[0].selected_source_names == ("archived-gefs",)
    assert report.input_audit[0].excluded_after_issue_names == ()
    assert report.validation_record()["input_audit"][0]["selected_records"][0]["sha256"] == "a" * 64
    assert report.promotion is False
    assert "aggregation-only" in report.promotion_blockers[0]


def test_hindcast_blocks_promotion_when_a_published_lead_is_missing() -> None:
    case = _complete_case()
    incomplete = HindcastCase(
        issue_time=case.issue_time,
        records=case.records,
        rows=tuple(row for row in case.rows if row.lead_day != 20),
    )

    report = run_hindcast((incomplete,))

    assert report.promotion is False
    assert any("lead 20" in blocker for blocker in report.promotion_blockers)


def test_hindcast_blocks_promotion_when_source_was_not_available_at_issue() -> None:
    case = _complete_case()
    leaky = HindcastCase(
        issue_time=case.issue_time,
        records=case.records + (_record(available_at=ISSUE_TIME + timedelta(days=1)),),
        rows=case.rows,
    )

    report = run_hindcast((leaky,))

    assert report.promotion is False
    assert any("after issue_time" in blocker for blocker in report.promotion_blockers)
    assert report.input_audit[0].excluded_after_issue_names == ("archived-gefs",)


def test_conditional_eta_cannot_be_labelled_as_observed_actual_et() -> None:
    with pytest.raises(ValueError, match="conditional ETa"):
        HindcastRow(
            layer="eta_well_watered_mm",
            lead_day=1,
            valid_date=date(2026, 7, 2),
            spatial_block="43:-117",
            p10=1.0,
            p50=2.0,
            p90=3.0,
            target_mm=2.0,
            target_kind="observed_actual_et",
            target_available_at=ISSUE_TIME + timedelta(days=2),
        )


def test_hindcast_rejects_a_reference_that_was_not_later_than_its_target_day() -> None:
    row = _row(layer="eto_mm", lead_day=1)
    with pytest.raises(ValueError, match="later than valid_date"):
        HindcastCase(
            issue_time=ISSUE_TIME,
            records=(_record(),),
            rows=(
                HindcastRow(
                    layer=row.layer,
                    lead_day=row.lead_day,
                    valid_date=row.valid_date,
                    spatial_block=row.spatial_block,
                    p10=row.p10,
                    p50=row.p50,
                    p90=row.p90,
                    target_mm=row.target_mm,
                    target_kind=row.target_kind,
                    target_available_at=datetime(
                        2026, 7, 2, tzinfo=timezone.utc
                    ),
                ),
            ),
        )


def test_fixture_cases_are_non_scientific_and_write_a_false_promotion_receipt(
    tmp_path: Path,
) -> None:
    case_path = _write_verified_evidence(tmp_path, classification="software_fixture")
    report, receipt = evaluate_hindcast_evidence(case_path)
    receipt_path = write_hindcast_validation(receipt, tmp_path / "validation.json")

    assert report.promotion is False
    assert "fixture" in report.promotion_blockers[0]
    assert "software fixture" in render_hindcast_markdown(report).lower()
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["promotion"] is False


def test_hindcast_cli_writes_fixture_receipts_and_returns_nonpromotion_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = _write_verified_evidence(tmp_path, classification="software_fixture")
    report = tmp_path / "hindcast.md"

    code = main(["hindcast-outlook", "--cases", str(cases), "--out", str(report)])

    assert code == 1
    assert report.exists()
    assert (tmp_path / "validation.json").exists()
    assert "promotion: false" in capsys.readouterr().out.lower()


def test_hindcast_cli_reports_invalid_case_input_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "hindcast-outlook",
            "--cases",
            str(tmp_path / "missing.json"),
            "--out",
            str(tmp_path / "hindcast.md"),
        ]
    )

    assert code == 2
    assert "cannot run outlook hindcast" in capsys.readouterr().err


def test_hindcast_cli_accepts_the_documented_private_tmp_verification_root() -> None:
    assert _trusted_hindcast_output(Path("/private/tmp/idaho_hindcast.md")) == Path(
        "/private/tmp/idaho_hindcast.md"
    )


def test_hindcast_cli_rejects_an_untrusted_output_location() -> None:
    with pytest.raises(ValueError, match="docs/results"):
        _trusted_hindcast_output(Path("/var/tmp/idaho_hindcast.md"))


def test_old_inline_perfect_rows_cannot_be_mixed_into_verified_evidence(tmp_path: Path) -> None:
    evidence_path = _write_verified_evidence(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["cases"][0]["rows"] = [
        {"layer": "eto_mm", "p10": 4.5, "p50": 4.5, "p90": 4.5, "target_mm": 4.5}
    ]
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ValueError, match="fields must match"):
        evaluate_hindcast_evidence(evidence_path)


def test_fabricated_target_value_or_time_cannot_promote(tmp_path: Path) -> None:
    evidence_path = _write_verified_evidence(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    target = tmp_path / "targets.json"
    original_target = target.read_text(encoding="utf-8")
    target_payload = json.loads(target.read_text(encoding="utf-8"))
    target_payload["values"][0]["target_mm"] = 999.0
    target.write_text(json.dumps(target_payload), encoding="utf-8")

    with pytest.raises(ValueError, match="target artifact sha256"):
        evaluate_hindcast_evidence(evidence_path)

    # An invented early availability timestamp is a separate temporal leak.
    target.write_text(original_target, encoding="utf-8")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["cases"][0]["target"]["available_at"] = "2026-07-02T00:00:00Z"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match immutable target artifact"):
        evaluate_hindcast_evidence(evidence_path)


def test_forged_public_report_cannot_write_a_promotion_receipt(tmp_path: Path) -> None:
    report = run_hindcast((_complete_case(),))
    # Promotion is derived from blockers, not a caller-settable report field.
    with pytest.raises(AttributeError):
        object.__setattr__(report, "promotion", True)
    with pytest.raises(ValueError, match="verified evaluation receipt"):
        write_hindcast_validation(report, tmp_path / "validation.json")


def test_missing_fixture_classification_is_not_promotable(tmp_path: Path) -> None:
    evidence_path = _write_verified_evidence(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    del evidence["evidence_classification"]
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ValueError, match="fields must match"):
        evaluate_hindcast_evidence(evidence_path)


def test_held_out_training_leakage_blocks_promotion(tmp_path: Path) -> None:
    evidence_path = _write_verified_evidence(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["cases"][0]["holdout"]["training_folds"].append(1)
    evidence["cases"][0]["holdout"]["training_seasons"].append("JJA")
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    report, receipt = evaluate_hindcast_evidence(evidence_path)

    assert report.promotion is False
    assert any("held-out spatial fold" in item for item in report.promotion_blockers)
    assert any("held-out season" in item for item in report.promotion_blockers)
    path = write_hindcast_validation(receipt, tmp_path / "validation.json")
    assert json.loads(path.read_text(encoding="utf-8"))["promotion"] is False
