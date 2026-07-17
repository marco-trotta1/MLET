"""Regression tests for the preregistered outlook hindcast release gate."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

import mlet.outlook.hindcast as hindcast_module
from mlet.outlook.hindcast import (
    AvailableRecord,
    build_release_authority_request,
    evaluate_hindcast_evidence,
    HindcastCase,
    HindcastRow,
    load_hindcast_cases,
    render_hindcast_markdown,
    run_hindcast,
    select_inputs_as_of,
    write_hindcast_validation,
    write_release_authority_request,
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


def _write_verified_evidence(
    tmp_path: Path,
    *,
    classification: str = "real_archived",
    issue_time: datetime = ISSUE_TIME,
    held_out_fold: int = 1,
) -> Path:
    """Create an archived byte bundle; values are never inline in the case file."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"archived source")
    issue = issue_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    collections = []
    target_values = []
    for lead in range(1, 21):
        valid = (issue_time.date() + timedelta(days=lead)).isoformat()
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
    forecast.write_text(json.dumps({"run_id": "PLACEHOLDER", "issued_at": issue, "fixture_non_scientific": False, "publication_classification": "production", "validation_status": "validated", "feature_collections": collections}), encoding="utf-8")
    manifest = build_manifest(issue, {"weather": source}, "test-revision", issue)
    # The output has to carry the manifest identity, then the manifest pins its exact bytes.
    forecast.write_text(json.dumps({"run_id": manifest.run_id, "issued_at": issue, "fixture_non_scientific": False, "publication_classification": "production", "validation_status": "validated", "feature_collections": collections}), encoding="utf-8")
    manifest = manifest.with_artifact_sha256({"outlook.json": hashlib.sha256(forecast.read_bytes()).hexdigest()})
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    target = tmp_path / "targets.json"
    case_id = f"{issue_time.strftime('%b').lower()}-fold-{held_out_fold}-{issue_time.date().isoformat()}"
    target_available = (issue_time + timedelta(days=22)).strftime("%Y-%m-%dT%H:%M:%SZ")
    target.write_text(json.dumps({"schema_version": 1, "kind": "idaho_outlook_hindcast_target", "receipt": {"case_id": case_id, "run_id": manifest.run_id, "uri": "https://archive.example.org/targets", "source_version": "target-v1", "available_at": target_available}, "values": target_values}), encoding="utf-8")
    receipt = {"schema_version": 1, "kind": "idaho_outlook_hindcast_source_receipt", "case_id": case_id, "run_id": manifest.run_id, "name": "weather", "available_at": issue, "source_version": "test-revision", "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "uri": source.resolve().as_uri()}
    source_receipt_path = tmp_path / "source-receipt.json"
    source_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    held_out_season = {1: "DJF", 4: "MAM", 7: "JJA", 10: "SON"}[issue_time.month]
    holdout = {"schema_version": 1, "kind": "idaho_outlook_hindcast_holdout_receipt", "case_id": case_id, "run_id": manifest.run_id, "uri": "https://archive.example.org/folds/v1", "source_version": "folds-v1", "sha256": "c" * 64, "available_at": issue, "spatial_block": "43:-117", "fold": held_out_fold, "held_out_fold": held_out_fold, "training_folds": [fold for fold in range(5) if fold != held_out_fold], "held_out_season": held_out_season, "training_seasons": [season for season in ("DJF", "MAM", "JJA", "SON") if season != held_out_season], "training_cutoff": issue, "calibration_cutoff": issue}
    holdout_path = tmp_path / "holdout-receipt.json"
    holdout_path.write_text(json.dumps(holdout), encoding="utf-8")
    assumptions = {}
    for name in ("water", "crop", "precip", "soil"):
        scenario = {**receipt, "kind": "idaho_outlook_hindcast_scenario_receipt", "name": name}
        path = tmp_path / f"{name}-receipt.json"
        path.write_text(json.dumps(scenario), encoding="utf-8")
        assumptions[name] = {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    evidence = {
        "schema_version": 3,
        "evidence_classification": classification,
        "provenance": {"uri": "https://archive.example.org/idaho", "version": "archive-v1", "sha256": "b" * 64, "available_at": issue},
        "cases": [{
            "case_id": case_id,
            "issue_time": issue,
            "forecast": {"run_id": manifest.run_id, "manifest_path": "manifest.json", "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "artifact_path": "outlook.json", "artifact_sha256": hashlib.sha256(forecast.read_bytes()).hexdigest()},
            "target": {"path": "targets.json", "uri": "https://archive.example.org/targets", "source_version": "target-v1", "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "available_at": target_available},
            "source_receipt_artifacts": [{"path": source_receipt_path.name, "sha256": hashlib.sha256(source_receipt_path.read_bytes()).hexdigest()}],
            "holdout_receipt": {"path": holdout_path.name, "sha256": hashlib.sha256(holdout_path.read_bytes()).hexdigest()},
            "scenario_receipt_artifacts": assumptions,
        }],
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    return evidence_path


def _write_qualifying_verified_evidence(tmp_path: Path) -> Path:
    """Build the complete five-fold/four-season archive required for promotion."""
    cases: list[dict[str, object]] = []
    for month in (1, 4, 7, 10):
        for fold in range(5):
            directory = f"case-{month:02d}-fold-{fold}"
            child = tmp_path / directory
            child.mkdir()
            child_evidence = _write_verified_evidence(
                child,
                issue_time=datetime(2026, month, 1, tzinfo=timezone.utc),
                held_out_fold=fold,
            )
            case = json.loads(child_evidence.read_text(encoding="utf-8"))["cases"][0]
            assert isinstance(case, dict)
            forecast = case["forecast"]
            target = case["target"]
            source_receipts = case["source_receipt_artifacts"]
            holdout = case["holdout_receipt"]
            scenarios = case["scenario_receipt_artifacts"]
            assert isinstance(forecast, dict) and isinstance(target, dict)
            assert isinstance(source_receipts, list) and isinstance(holdout, dict) and isinstance(scenarios, dict)
            forecast["manifest_path"] = f"{directory}/{forecast['manifest_path']}"
            forecast["artifact_path"] = f"{directory}/{forecast['artifact_path']}"
            target["path"] = f"{directory}/{target['path']}"
            for receipt in source_receipts:
                assert isinstance(receipt, dict)
                receipt["path"] = f"{directory}/{receipt['path']}"
            holdout["path"] = f"{directory}/{holdout['path']}"
            for receipt in scenarios.values():
                assert isinstance(receipt, dict)
                receipt["path"] = f"{directory}/{receipt['path']}"
            cases.append(case)
    evidence = {
        "schema_version": 3,
        "evidence_classification": "real_archived",
        "provenance": {
            "uri": "https://archive.example.org/idaho",
            "version": "archive-v1",
            "sha256": "b" * 64,
            "available_at": "2026-01-01T00:00:00Z",
        },
        "cases": cases,
    }
    evidence_path = tmp_path / "qualifying-evidence.json"
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
    assert (tmp_path / "authority_request.json").exists()
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


def test_hindcast_cli_has_no_local_promotion_signing_command() -> None:
    with pytest.raises(SystemExit) as error:
        main(["attest-hindcast-outlook"])

    assert error.value.code == 2


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
    with pytest.raises(ValueError, match="evaluation receipt"):
        write_hindcast_validation(report, tmp_path / "validation.json")


def test_missing_fixture_classification_is_not_promotable(tmp_path: Path) -> None:
    evidence_path = _write_verified_evidence(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    del evidence["evidence_classification"]
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ValueError, match="fields must match"):
        evaluate_hindcast_evidence(evidence_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("fixture_non_scientific", None, "non-boolean"),
        ("fixture_non_scientific", "false", "non-boolean"),
        ("fixture_non_scientific", True, "software fixture"),
        ("publication_classification", "research", "not production"),
        ("validation_status", "not_validated", "not validated"),
    ],
)
def test_forecast_classification_must_be_exact_to_be_promotable(
    tmp_path: Path, field: str, value: object, message: str,
) -> None:
    evidence_path = _write_verified_evidence(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    forecast_path = tmp_path / "outlook.json"
    forecast = json.loads(forecast_path.read_text(encoding="utf-8"))
    forecast[field] = value
    forecast_path.write_text(json.dumps(forecast), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest = build_manifest(ISSUE_TIME.strftime("%Y-%m-%dT%H:%M:%SZ"), {"weather": tmp_path / "source.bin"}, "test-revision", ISSUE_TIME.strftime("%Y-%m-%dT%H:%M:%SZ"))
    # Preserve the original run identity while repinning its changed forecast bytes.
    original = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.run_id == original["run_id"]
    manifest = manifest.with_artifact_sha256({"outlook.json": hashlib.sha256(forecast_path.read_bytes()).hexdigest()})
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    evidence["cases"][0]["forecast"]["artifact_sha256"] = hashlib.sha256(forecast_path.read_bytes()).hexdigest()
    evidence["cases"][0]["forecast"]["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    report, _receipt = evaluate_hindcast_evidence(evidence_path)

    assert report.promotion is False
    assert any(message in blocker for blocker in report.promotion_blockers)


def test_altered_receipt_bytes_and_inline_receipts_are_rejected(tmp_path: Path) -> None:
    evidence_path = _write_verified_evidence(tmp_path)
    scenario_path = tmp_path / "water-receipt.json"
    scenario_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="sha256"):
        evaluate_hindcast_evidence(evidence_path)

    evidence_path = _write_verified_evidence(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["cases"][0]["source_receipts"] = []
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match="fields must match"):
        evaluate_hindcast_evidence(evidence_path)


def test_qualifying_archived_evidence_is_only_an_external_release_candidate(
    tmp_path: Path,
) -> None:
    evidence_path = _write_qualifying_verified_evidence(tmp_path)

    report, receipt = evaluate_hindcast_evidence(evidence_path)
    validation_path = write_hindcast_validation(receipt, tmp_path / "validation.json")
    request_path = write_release_authority_request(receipt, tmp_path / "authority_request.json")
    request = build_release_authority_request(evidence_path)

    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    written_request = json.loads(request_path.read_text(encoding="utf-8"))
    assert report.promotion is False
    assert report.promotion_blockers == ("requires_separately_trusted_release_authority",)
    assert validation["promotion"] is False
    assert validation["publication_authority"] == "requires_separately_trusted_release_authority"
    assert written_request == request
    assert request["promotion"] is False
    assert request["promotion_blockers"] == ["requires_separately_trusted_release_authority"]
    assert request["external_release_eligible"] is True


def test_hindcast_cli_emits_a_qualified_candidate_but_exits_one(
    tmp_path: Path,
) -> None:
    evidence_path = _write_qualifying_verified_evidence(tmp_path)
    report_path = tmp_path / "hindcast.md"

    code = main(["hindcast-outlook", "--cases", str(evidence_path), "--out", str(report_path)])

    request = json.loads((tmp_path / "authority_request.json").read_text(encoding="utf-8"))
    validation = json.loads((tmp_path / "validation.json").read_text(encoding="utf-8"))
    assert code == 1
    assert request["external_release_eligible"] is True
    assert request["promotion"] is False
    assert validation["promotion"] is False


def test_runtime_authority_monkeypatches_cannot_cause_local_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_path = _write_qualifying_verified_evidence(tmp_path)
    monkeypatch.setattr(hindcast_module, "_PINNED_PROMOTION_AUTHORITY", object(), raising=False)
    monkeypatch.setenv("MLET_HINDCAST_PROMOTION_PUBLIC_KEY", "attacker-selected")
    monkeypatch.setenv("MLET_HINDCAST_PROMOTION_PRIVATE_KEY", "attacker-selected")

    report, receipt = evaluate_hindcast_evidence(evidence_path)
    assert report.promotion is False
    object.__setattr__(receipt.report, "promotion_blockers", ())
    assert receipt.report.promotion is False
    validation_path = write_hindcast_validation(receipt, tmp_path / "validation.json")
    request_path = write_release_authority_request(receipt, tmp_path / "authority_request.json")

    assert json.loads(validation_path.read_text(encoding="utf-8"))["promotion"] is False
    assert json.loads(request_path.read_text(encoding="utf-8"))["promotion"] is False


def test_held_out_training_leakage_blocks_promotion(tmp_path: Path) -> None:
    evidence_path = _write_verified_evidence(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    holdout_path = tmp_path / "holdout-receipt.json"
    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    holdout["training_folds"].append(1)
    holdout["training_seasons"].append("JJA")
    holdout_path.write_text(json.dumps(holdout), encoding="utf-8")
    evidence["cases"][0]["holdout_receipt"]["sha256"] = hashlib.sha256(holdout_path.read_bytes()).hexdigest()
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    report, receipt = evaluate_hindcast_evidence(evidence_path)

    assert report.promotion is False
    assert any("held-out spatial fold" in item for item in report.promotion_blockers)
    assert any("held-out season" in item for item in report.promotion_blockers)
    path = write_hindcast_validation(receipt, tmp_path / "validation.json")
    assert json.loads(path.read_text(encoding="utf-8"))["promotion"] is False
