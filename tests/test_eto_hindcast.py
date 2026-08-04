"""Tests for the ETo-only, evidence-bound hindcast contract."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from mlet.outlook.dates import outlook_valid_date
from mlet.outlook.eto_hindcast import (
    evaluate_eto_hindcast_evidence,
    write_eto_hindcast_json,
    write_eto_hindcast_markdown,
)
from mlet.outlook.eto_archive import combine_eto_hindcast_evidence
from mlet.manuscript_artifacts import build_eto_hindcast_artifacts
from mlet.outlook.manifest import build_manifest
from mlet.cli import main


_ISSUE_TIME = datetime(2026, 7, 1, 18, tzinfo=timezone.utc)
_VALIDATION_SCOPE = {
    "formal_hindcast_layers": ["eto_mm"],
    "nonforecast_analysis_layers": ["eta_analysis_mm"],
    "unvalidated_projection_layers": [
        "potential_et_c_mm",
        "eta_well_watered_mm",
        "eta_no_irrigation_mm",
    ],
}


def _write_eto_evidence(tmp_path: Path) -> Path:
    source = tmp_path / "weather.jsonl"
    source.write_text('{"weather":"archived"}\n', encoding="utf-8")
    issue = _ISSUE_TIME.strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = build_manifest(issue, {"weather": source}, "test-revision", issue)
    collections = []
    targets = []
    for lead_day in range(1, 21):
        valid_date = outlook_valid_date(_ISSUE_TIME, lead_day).isoformat()
        collections.append(
            {
                "type": "FeatureCollection",
                "valid_date": valid_date,
                "lead_day": lead_day,
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [-116.5, 43.5],
                        },
                        "properties": {
                            "grid_id": "43:-117",
                            "valid_date": valid_date,
                            "lead_day": lead_day,
                            "layers": {
                                "eto_mm": {"p10": 3.0, "p50": 4.0, "p90": 5.0}
                            },
                        }
                    }
                ],
            }
        )
        targets.append(
            {
                "target_id": "agrimet:test",
                "grid_id": "43:-117",
                "latitude": 43.5,
                "longitude": -116.5,
                "lead_day": lead_day,
                "valid_date": valid_date,
                "target_mm": 4.5,
                "baseline_p50_mm": 4.25,
                "target_kind": "independent_asce_short_reference_eto",
            }
        )
    forecast = tmp_path / "outlook.json"
    forecast.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": manifest.run_id,
                "issued_at": issue,
                "fixture_non_scientific": False,
                "production_status": "research_candidate",
                "promotion_status": "not_promoted",
                "validation_status": "evaluation_pending",
                "validation_scope": _VALIDATION_SCOPE,
                "layers": {
                    "eto_mm": {
                        "units": "mm/day",
                        "kind": "forecast_ensemble_quantiles",
                        "validation_role": "formal_hindcast_target",
                        "definition": "ASCE short-reference ET from weather-ensemble members.",
                    }
                },
                "feature_collections": collections,
            }
        ),
        encoding="utf-8",
    )
    manifest = manifest.with_artifact_sha256(
        {"outlook.json": hashlib.sha256(forecast.read_bytes()).hexdigest()}
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")
    case_id = "eto-only-case"
    target_available = (_ISSUE_TIME + timedelta(days=22)).strftime("%Y-%m-%dT%H:%M:%SZ")
    target_path = tmp_path / "targets.json"
    target_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "kind": "idaho_outlook_eto_hindcast_target",
                "receipt": {
                    "case_id": case_id,
                    "run_id": manifest.run_id,
                    "uri": "https://archive.example.org/targets",
                    "source_version": "agrimet-v1",
                    "available_at": target_available,
                },
                "values": targets,
            }
        ),
        encoding="utf-8",
    )
    source_receipt_path = tmp_path / "weather-receipt.json"
    source_receipt_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "idaho_outlook_hindcast_source_receipt",
                "case_id": case_id,
                "run_id": manifest.run_id,
                "name": "weather",
                "uri": source.resolve().as_uri(),
                "source_version": "test-revision",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "available_at": issue,
            }
        ),
        encoding="utf-8",
    )
    holdout_path = tmp_path / "holdout-receipt.json"
    holdout_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "idaho_outlook_hindcast_holdout_receipt",
                "case_id": case_id,
                "run_id": manifest.run_id,
                "uri": "https://archive.example.org/folds/v1",
                "source_version": "folds-v1",
                "sha256": "c" * 64,
                "available_at": issue,
                "held_out_fold": 4,
                "training_folds": [0, 1, 2, 3],
                "held_out_season": "JJA",
                "training_seasons": ["DJF", "MAM", "SON"],
                "training_cutoff": issue,
                "calibration_cutoff": issue,
            }
        ),
        encoding="utf-8",
    )
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": 4,
                "evidence_classification": "real_archived",
                "validation_scope": _VALIDATION_SCOPE,
                "provenance": {
                    "uri": "https://archive.example.org/idaho",
                    "version": "archive-v1",
                    "sha256": "b" * 64,
                    "available_at": issue,
                },
                "cases": [
                    {
                        "case_id": case_id,
                        "issue_time": issue,
                        "forecast": {
                            "run_id": manifest.run_id,
                            "manifest_path": manifest_path.name,
                            "manifest_sha256": hashlib.sha256(
                                manifest_path.read_bytes()
                            ).hexdigest(),
                            "artifact_path": forecast.name,
                            "artifact_sha256": hashlib.sha256(
                                forecast.read_bytes()
                            ).hexdigest(),
                        },
                        "target": {
                            "path": target_path.name,
                            "uri": "https://archive.example.org/targets",
                            "source_version": "agrimet-v1",
                            "sha256": hashlib.sha256(target_path.read_bytes()).hexdigest(),
                            "available_at": target_available,
                        },
                        "source_receipt_artifacts": [
                            {
                                "path": source_receipt_path.name,
                                "sha256": hashlib.sha256(
                                    source_receipt_path.read_bytes()
                                ).hexdigest(),
                            }
                        ],
                        "holdout_receipt": {
                            "path": holdout_path.name,
                            "sha256": hashlib.sha256(holdout_path.read_bytes()).hexdigest(),
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return evidence_path


def test_eto_only_evidence_scores_eto_without_scenario_receipts(tmp_path: Path) -> None:
    """Removing a scenario receipt must not block the ETo-only evaluation."""
    evidence_path = _write_eto_evidence(tmp_path)

    report = evaluate_eto_hindcast_evidence(evidence_path)

    metric = next(
        item
        for item in report.metrics
        if item.group == "lead_day" and item.key == "1"
    )
    assert metric.sample_count == 1
    assert metric.mae_mm == pytest.approx(0.5)
    assert metric.mean_pinball_loss_mm == pytest.approx(0.15)
    assert metric.baseline_mae_mm == pytest.approx(0.25)
    assert metric.mae_improvement_mm == pytest.approx(-0.25)
    assert report.validation_scope == _VALIDATION_SCOPE
    assert not any("scenario" in blocker for blocker in report.completion_blockers)
    assert not any("recomputed station fold" in blocker for blocker in report.completion_blockers)
    assert any(
        "lead_season_spatial_fold 1:JJA:4" in blocker
        for blocker in report.completion_blockers
    )


def test_eto_hindcast_markdown_states_the_evaluation_boundary(tmp_path: Path) -> None:
    """Removing the claim boundary must fail the public result artifact."""
    report = evaluate_eto_hindcast_evidence(_write_eto_evidence(tmp_path))
    destination = tmp_path / "eto-hindcast.md"

    write_eto_hindcast_markdown(report, destination)

    markdown = destination.read_text(encoding="utf-8")
    assert "# Idaho ETo Hindcast Diagnostic" in markdown
    assert "Mean pinball loss" in markdown
    assert "does not validate ETc or ETa" in markdown


def test_eto_hindcast_json_preserves_the_machine_readable_metric_record(
    tmp_path: Path,
) -> None:
    """Dropping pinball loss must fail the manuscript result record."""
    report = evaluate_eto_hindcast_evidence(_write_eto_evidence(tmp_path))
    destination = tmp_path / "eto-hindcast.json"

    write_eto_hindcast_json(report, destination)

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["kind"] == "idaho_eto_hindcast_result"
    assert payload["validation_scope"] == _VALIDATION_SCOPE
    assert payload["metrics"][0]["mean_pinball_loss_mm"] >= 0.0
    assert len(payload["evidence_sha256"]) == 64
    assert payload["archive_sha256"] == payload["evidence_sha256"]
    assert len(payload["evaluation_sha256"]) == 64
    assert payload["forecast_revisions"] == ["test-revision"]
    assert payload["source_versions"] == payload["target_sources"]
    assert payload["exclusions"] == []
    assert payload["support"]["cell_count"] == 400
    assert payload["claim_safe_prose"]["scope"] == "MLET formally evaluates eto_mm only."
    assert payload["target_count"] == 20
    assert payload["station_count"] == 1
    assert payload["target_sources"] == [
        {
            "uri": "https://archive.example.org/targets",
            "source_version": "agrimet-v1",
        }
    ]


def test_complete_evaluator_result_feeds_the_manuscript_generator(tmp_path: Path) -> None:
    report = evaluate_eto_hindcast_evidence(_write_eto_evidence(tmp_path))
    result_path = tmp_path / "eto-hindcast.json"
    write_eto_hindcast_json(report, result_path)
    output = tmp_path / "artifacts"
    output.mkdir()

    with pytest.raises(ValueError, match="incomplete"):
        build_eto_hindcast_artifacts(result_path, output)


def test_eto_hindcast_cli_writes_an_eto_only_diagnostic(tmp_path: Path) -> None:
    """Removing the v4 command must fail the ETo-only command contract."""
    evidence_path = _write_eto_evidence(tmp_path)
    output = tmp_path / "eto-hindcast.md"

    code = main(["hindcast-eto", "--cases", str(evidence_path), "--out", str(output)])

    assert code == 1
    assert "does not validate ETc or ETa" in output.read_text(encoding="utf-8")
    assert (tmp_path / "eto-hindcast.json").exists()


def test_nested_outlook_hindcast_alias_uses_the_e_to_branch(tmp_path: Path) -> None:
    evidence_path = _write_eto_evidence(tmp_path)
    output = tmp_path / "nested-eto-hindcast.md"

    code = main(
        [
            "outlook",
            "hindcast",
            "--evidence",
            str(evidence_path),
            "--output",
            str(output),
        ]
    )

    assert code == 1
    assert "does not validate ETc or ETa" in output.read_text(encoding="utf-8")


def test_eto_hindcast_rejects_a_target_descriptor_with_a_different_source(
    tmp_path: Path,
) -> None:
    """The evidence descriptor must not relabel the independent target source."""
    evidence_path = _write_eto_evidence(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["cases"][0]["target"]["uri"] = "https://example.test/not-agrimet"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ValueError, match="target artifact receipt URI"):
        evaluate_eto_hindcast_evidence(evidence_path)


def test_eto_evidence_bundler_rewrites_one_valid_case_below_an_immutable_root(
    tmp_path: Path,
) -> None:
    """A full archive must not depend on files outside its final evidence root."""
    source_root = tmp_path / "source"
    source_root.mkdir()
    evidence_path = _write_eto_evidence(source_root)
    destination = tmp_path / "bundle"
    destination.mkdir()

    bundled = combine_eto_hindcast_evidence((evidence_path,), destination)

    report = evaluate_eto_hindcast_evidence(bundled)
    payload = json.loads(bundled.read_text(encoding="utf-8"))
    assert report.case_count == 1
    assert payload["cases"][0]["forecast"]["artifact_path"].startswith("cases/")
