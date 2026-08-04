"""Tests for the public ETo archive assembler."""

from __future__ import annotations

from pathlib import Path
import json

from mlet.outlook.archive import build_eto_hindcast_archive, bundle_eto_hindcast_evidence
from mlet.outlook.eto_hindcast import evaluate_eto_hindcast_evidence

from tests.test_eto_hindcast import _write_eto_evidence


def test_public_archive_assembler_returns_a_self_contained_evidence_root(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    evidence_path = _write_eto_evidence(source_root)
    destination = tmp_path / "archive"
    destination.mkdir()

    result_path = bundle_eto_hindcast_evidence((evidence_path,), destination)

    assert result_path == destination / "evidence.json"
    assert evaluate_eto_hindcast_evidence(result_path).case_count == 1


def test_index_archive_assembler_creates_cases_and_index_receipt(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_eto_evidence(source_root)
    (source_root / "gefs-index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "mlet.eto.gefs-index",
                "issues": [
                    {
                        "case_id": "eto-only-case",
                        "issue_time": "2026-07-01T18:00:00Z",
                        "forecast_directory": ".",
                        "source_available_at": {"weather": "2026-07-01T18:00:00Z"},
                        "held_out_fold": 4,
                        "held_out_season": "JJA",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (source_root / "agrimet-index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "mlet.eto.agrimet-index",
                "targets": [{"case_id": "eto-only-case", "target_path": "targets.json"}],
            }
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "archive"
    destination.mkdir()

    result_path = build_eto_hindcast_archive(
        source_root / "gefs-index.json",
        source_root / "agrimet-index.json",
        destination,
    )

    assert evaluate_eto_hindcast_evidence(result_path).case_count == 1
    assert (destination / "archive-index-receipt.json").is_file()
    assert (destination / "gefs-index.json").is_file()
    assert (destination / "agrimet-index.json").is_file()
