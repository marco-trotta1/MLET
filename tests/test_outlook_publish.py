"""Software contracts for the standalone, non-promotable outlook map."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import MappingProxyType

import pytest

from mlet.cli import main
from mlet.outlook.build import PublishedRun, build_outlook, read_published_run
from mlet.outlook.publish import publish_outlook


WEATHER_FIXTURE = Path("examples/outlook/weather_members.jsonl")
STATE_FIXTURE = Path("examples/outlook/state.jsonl")
CROP_FIXTURE = Path("examples/outlook/crop_grid.jsonl")


def _fixture_run(tmp_path: Path) -> Path:
    result = build_outlook(
        weather_path=WEATHER_FIXTURE,
        state_path=STATE_FIXTURE,
        crop_path=CROP_FIXTURE,
        out_dir=tmp_path,
    )
    return tmp_path / result.run_id


def test_publish_writes_a_standalone_non_scientific_research_candidate(
    tmp_path: Path,
) -> None:
    run = _fixture_run(tmp_path)
    result = publish_outlook(run, out_dir=tmp_path / "map")

    assert result.fixture_non_scientific is True
    assert {path.name for path in result.output_dir.iterdir()} == {
        "index.html",
        "outlook.geojson",
        "serve-contract.json",
        "summary.json",
    }
    contract = json.loads(result.serve_contract_path.read_text())
    geojson = json.loads(result.geojson_path.read_text())
    summary = json.loads(result.summary_path.read_text())
    assert contract["promotion"] is False
    assert contract["promotion_status"] == "not_promoted"
    assert contract["validation_status"] == "validation_pending"
    assert contract["fixture_non_scientific"] is True
    assert geojson["type"] == "FeatureCollection"
    assert geojson["promotion"] is False
    assert geojson["promotion_status"] == "not_promoted"
    assert summary["promotion"] is False
    assert summary["promotion_status"] == "not_promoted"
    feature = geojson["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    assert feature["properties"]["spatial_resolution"] == "native_weather_grid"
    assert feature["properties"]["validation_status"] == "validation_pending"
    assert feature["properties"]["promotion_status"] == "not_promoted"
    assert summary["not_field_scale"] is True
    assert summary["regional_aggregation"] == "equal_cell_descriptive_mean_not_area_weighted"
    assert "source-grid cell areas" in summary["regional_aggregation_note"].lower()

    index = result.index_path.read_text()
    for label in (
        "ETo outlook",
        "Potential crop ET (well-watered)",
        "Latest ETa analysis",
        "ETa scenario: well-watered",
        "ETa scenario: no further irrigation",
        "Regional outlook — not a field-level irrigation recommendation",
        "NON-SCIENTIFIC SOFTWARE FIXTURE",
        "ETa observation date",
        "2026-07-14",
    ):
        assert label in index


def test_publisher_forces_false_status_even_if_an_in_memory_source_claims_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _fixture_run(tmp_path)
    verified = read_published_run(tmp_path, run.name)
    altered = json.loads(verified.artifact_bytes("outlook.json"))
    altered["promotion"] = True
    altered["promotion_status"] = "promoted"
    altered["validation_status"] = "validated"
    mutated = PublishedRun(
        run_id=verified.run_id,
        manifest=verified.manifest,
        artifacts=MappingProxyType(
            {**verified.artifacts, "outlook.json": json.dumps(altered).encode("utf-8")}
        ),
    )
    monkeypatch.setattr("mlet.outlook.publish.read_published_run", lambda _root, _run: mutated)
    monkeypatch.setenv("MLET_PROMOTION", "true")

    result = publish_outlook(run, out_dir=tmp_path / "candidate")

    contract = json.loads(result.serve_contract_path.read_text())
    assert contract["promotion"] is False
    assert contract["promotion_status"] == "not_promoted"
    assert contract["validation_status"] == "validation_pending"


def test_publisher_refuses_a_run_with_a_mutated_validation_receipt(tmp_path: Path) -> None:
    run = _fixture_run(tmp_path)
    private_generation = run.parent / os.readlink(run)
    receipt = private_generation / "validation.json"
    payload = json.loads(receipt.read_text())
    payload["promotion"] = True
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        publish_outlook(run, out_dir=tmp_path / "candidate")


def test_publish_cli_writes_candidate_but_returns_pending_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _fixture_run(tmp_path)

    assert main(["publish-outlook", "--run", str(run), "--out", str(tmp_path / "map")]) == 1

    output = capsys.readouterr().out
    assert "index: " in output
    assert "schema_version: 1" in output
    assert "promotion: false" in output
    assert "validation: pending" in output


def test_publish_cli_returns_two_for_an_unreadable_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["publish-outlook", "--run", str(tmp_path / "missing-run")]) == 2
    assert "cannot publish outlook candidate" in capsys.readouterr().err


def test_publish_escapes_hostile_source_data_and_uses_dom_text_nodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _fixture_run(tmp_path)
    verified = read_published_run(tmp_path, run.name)
    altered = json.loads(verified.artifact_bytes("outlook.json"))
    hostile_grid_id = '</script><script>window.mletPwned=true</script><img src=x>'
    altered["feature_collections"][0]["features"][0]["properties"]["grid_id"] = hostile_grid_id
    mutated = PublishedRun(
        run_id=verified.run_id,
        manifest=verified.manifest,
        artifacts=MappingProxyType(
            {**verified.artifacts, "outlook.json": json.dumps(altered).encode("utf-8")}
        ),
    )
    monkeypatch.setattr("mlet.outlook.publish.read_published_run", lambda _root, _run: mutated)

    result = publish_outlook(run, out_dir=tmp_path / "candidate")

    index = result.index_path.read_text(encoding="utf-8")
    assert hostile_grid_id not in index
    assert "\\u003c/script\\u003e\\u003cscript\\u003e" in index
    assert "map.innerHTML" not in index
    assert "document.createElementNS" in index
    assert "title.textContent" in index


def test_publish_failure_never_exposes_a_partial_candidate_and_is_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _fixture_run(tmp_path)
    destination = tmp_path / "candidate"
    from mlet.outlook import publish as outlook_publish

    original_write = outlook_publish._write_new_bytes_at
    attempts = 0

    def fail_second_write(directory_fd: int, filename: str, contents: bytes) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise OSError("simulated write failure")
        original_write(directory_fd, filename, contents)

    monkeypatch.setattr(outlook_publish, "_write_new_bytes_at", fail_second_write)
    with pytest.raises(OSError, match="simulated write failure"):
        publish_outlook(run, out_dir=destination)

    assert not destination.exists()
    assert list(tmp_path.glob(".candidate.building-*"))

    monkeypatch.setattr(outlook_publish, "_write_new_bytes_at", original_write)
    result = publish_outlook(run, out_dir=destination)
    assert result.output_dir.is_symlink()
    assert {path.name for path in result.output_dir.iterdir()} == {
        "index.html",
        "outlook.geojson",
        "serve-contract.json",
        "summary.json",
    }
