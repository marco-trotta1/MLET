"""Non-scientific checks for reproducible CDL grid aggregation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mlet.sources.cdl import GridCell, aggregate_cdl


def _write_intersections(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(rows), encoding="utf-8")


def _grid_cells() -> list[GridCell]:
    return [GridCell(grid_id="fixture-idaho-grid", area_m2=100.0)]


def _cdl_rows() -> list[dict[str, object]]:
    return [
        {
            "grid_id": "fixture-idaho-grid",
            "crop_code": 1,
            "area_m2": 60.0,
            "confidence": 90.0,
            "source_year": 2025,
        },
        {
            "grid_id": "fixture-idaho-grid",
            "crop_code": 36,
            "area_m2": 30.0,
            "confidence": 80.0,
            "source_year": 2025,
        },
    ]


def test_cdl_aggregation_retains_year_confidence_and_area_weighted_fractions(
    tmp_path: Path,
) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    _write_intersections(cdl_path, _cdl_rows())

    fractions = aggregate_cdl(cdl_path, _grid_cells(), source_year=2025)

    assert [item.crop_code for item in fractions] == ["1", "36"]
    assert [item.fraction for item in fractions] == [0.6, 0.3]
    assert all(item.coverage_fraction == 0.9 for item in fractions)
    assert all(item.source_year == 2025 for item in fractions)
    assert fractions[0].confidence_pct == pytest.approx(90.0)
    assert fractions[1].confidence_pct == pytest.approx(80.0)


def test_cdl_aggregation_emits_unknown_below_coverage_threshold(tmp_path: Path) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    rows = _cdl_rows()
    rows[1]["area_m2"] = 19.0
    _write_intersections(cdl_path, rows)

    fractions = aggregate_cdl(cdl_path, _grid_cells(), source_year=2025)

    assert len(fractions) == 1
    assert fractions[0].crop_class == "unknown"
    assert fractions[0].fraction == 0.0
    assert fractions[0].coverage_fraction == pytest.approx(0.79)


def test_cdl_aggregation_rejects_unrecorded_or_mismatched_source_year(tmp_path: Path) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    rows = _cdl_rows()
    del rows[0]["source_year"]
    _write_intersections(cdl_path, rows)

    with pytest.raises(ValueError, match="source_year"):
        aggregate_cdl(cdl_path, _grid_cells(), source_year=2025)

    rows = _cdl_rows()
    rows[0]["source_year"] = 2026
    _write_intersections(cdl_path, rows)
    with pytest.raises(ValueError, match="source_year"):
        aggregate_cdl(cdl_path, _grid_cells(), source_year=2025)


def test_cdl_aggregation_rejects_crop_fraction_outside_grid_area(tmp_path: Path) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    rows = _cdl_rows()
    rows[1]["area_m2"] = 50.0
    _write_intersections(cdl_path, rows)

    with pytest.raises(ValueError, match="coverage"):
        aggregate_cdl(cdl_path, _grid_cells(), source_year=2025)


def test_cdl_fixture_is_conspicuously_non_scientific() -> None:
    fractions = aggregate_cdl(
        Path("examples/outlook/crop_grid.jsonl"), _grid_cells(), source_year=2025
    )

    assert all(item.crop_class.startswith("fixture_") for item in fractions)
