"""Software-only checks for reproducible, issue-time-gated CDL aggregation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mlet.sources.cdl import CdlLayerMetadata, GridCell, aggregate_cdl


ISSUED_AT = "2026-07-16T00:00:00Z"
LEGEND_URL = (
    "https://www.nass.usda.gov/Research_and_Science/Cropland/metadata/"
    "metadata_Cropland-Data-Layer-2024.htm"
)


def _write_intersections(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(json.dumps(rows, sort_keys=True), encoding="utf-8")


def _metadata(path: Path, *, release_at: str = "2025-02-27T00:00:00Z") -> CdlLayerMetadata:
    return CdlLayerMetadata(
        source_year=2024,
        layer_version="2024-edition",
        legend_version="usda-nass-cdl-2024",
        release_at=release_at,
        upstream_uri=LEGEND_URL,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def _grid_cells() -> list[GridCell]:
    return [GridCell(grid_id="fixture-idaho-grid", area_m2=100.0)]


def _cdl_rows() -> list[dict[str, object]]:
    return [
        {
            "grid_id": "fixture-idaho-grid",
            "crop_code": 1,
            "area_m2": 60.0,
            "confidence": 90.0,
            "source_year": 2024,
        },
        {
            "grid_id": "fixture-idaho-grid",
            "crop_code": 36,
            "area_m2": 30.0,
            "confidence": 80.0,
            "source_year": 2024,
        },
    ]


def test_cdl_aggregation_retains_immutable_layer_metadata_and_area_weighted_fractions(
    tmp_path: Path,
) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    _write_intersections(cdl_path, _cdl_rows())
    layer = _metadata(cdl_path)

    fractions = aggregate_cdl(
        cdl_path,
        _grid_cells(),
        source_year=2024,
        issued_at=ISSUED_AT,
        layer_metadata=layer,
    )

    assert [item.crop_code for item in fractions] == ["1", "36"]
    assert [item.fraction for item in fractions] == [0.6, 0.3]
    assert all(item.coverage_fraction == 0.9 for item in fractions)
    assert all(item.source_year == 2024 for item in fractions)
    assert all(item.layer_metadata == layer for item in fractions)
    assert fractions[0].confidence_pct == pytest.approx(90.0)
    assert fractions[1].confidence_pct == pytest.approx(80.0)


def test_cdl_aggregation_rejects_layer_released_after_historical_issue(tmp_path: Path) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    _write_intersections(cdl_path, _cdl_rows())

    with pytest.raises(ValueError, match="release_at"):
        aggregate_cdl(
            cdl_path,
            _grid_cells(),
            source_year=2024,
            issued_at="2024-12-31T00:00:00Z",
            layer_metadata=_metadata(cdl_path),
        )


def test_cdl_aggregation_rejects_unrecorded_mismatched_or_out_of_scope_source_year(
    tmp_path: Path,
) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    rows = _cdl_rows()
    del rows[0]["source_year"]
    _write_intersections(cdl_path, rows)

    with pytest.raises(ValueError, match="source_year"):
        aggregate_cdl(
            cdl_path,
            _grid_cells(),
            source_year=2024,
            issued_at=ISSUED_AT,
            layer_metadata=_metadata(cdl_path),
        )

    rows = _cdl_rows()
    rows[0]["source_year"] = 2025
    _write_intersections(cdl_path, rows)
    with pytest.raises(ValueError, match="source_year"):
        aggregate_cdl(
            cdl_path,
            _grid_cells(),
            source_year=2024,
            issued_at=ISSUED_AT,
            layer_metadata=_metadata(cdl_path),
        )

    rows = _cdl_rows()
    rows.append(
        {
            "grid_id": "not-requested-grid",
            "crop_code": 1,
            "area_m2": 1.0,
            "confidence": 90.0,
            "source_year": 2025,
        }
    )
    _write_intersections(cdl_path, rows)
    with pytest.raises(ValueError, match="source_year"):
        aggregate_cdl(
            cdl_path,
            _grid_cells(),
            source_year=2024,
            issued_at=ISSUED_AT,
            layer_metadata=_metadata(cdl_path),
        )


def test_cdl_aggregation_rejects_metadata_checksum_or_unsupported_legend(tmp_path: Path) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    _write_intersections(cdl_path, _cdl_rows())
    layer = _metadata(cdl_path)

    with pytest.raises(ValueError, match="checksum"):
        aggregate_cdl(
            cdl_path,
            _grid_cells(),
            source_year=2024,
            issued_at=ISSUED_AT,
            layer_metadata=CdlLayerMetadata(
                source_year=layer.source_year,
                layer_version=layer.layer_version,
                legend_version=layer.legend_version,
                release_at=layer.release_at,
                upstream_uri=layer.upstream_uri,
                sha256="0" * 64,
            ),
        )

    with pytest.raises(ValueError, match="legend"):
        aggregate_cdl(
            cdl_path,
            _grid_cells(),
            source_year=2024,
            issued_at=ISSUED_AT,
            layer_metadata=CdlLayerMetadata(
                source_year=layer.source_year,
                layer_version=layer.layer_version,
                legend_version="usda-nass-cdl-2023",
                release_at=layer.release_at,
                upstream_uri=layer.upstream_uri,
                sha256=layer.sha256,
            ),
        )


@pytest.mark.parametrize("bad_code", ("not-a-cdl-code", 999, 7))
def test_cdl_aggregation_rejects_non_numeric_or_unrecognized_2024_legend_codes(
    tmp_path: Path, bad_code: object
) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    rows = _cdl_rows()
    rows[0]["crop_code"] = bad_code
    _write_intersections(cdl_path, rows)

    with pytest.raises(ValueError, match="legend"):
        aggregate_cdl(
            cdl_path,
            _grid_cells(),
            source_year=2024,
            issued_at=ISSUED_AT,
            layer_metadata=_metadata(cdl_path),
        )


def test_cdl_aggregation_represents_background_as_non_crop(tmp_path: Path) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    rows = _cdl_rows()
    rows[1] = {
        "grid_id": "fixture-idaho-grid",
        "crop_code": 0,
        "area_m2": 30.0,
        "confidence": 80.0,
        "source_year": 2024,
    }
    _write_intersections(cdl_path, rows)

    fractions = aggregate_cdl(
        cdl_path,
        _grid_cells(),
        source_year=2024,
        issued_at=ISSUED_AT,
        layer_metadata=_metadata(cdl_path),
    )

    non_crop = next(item for item in fractions if item.crop_class == "non_crop")
    assert non_crop.crop_code is None
    assert non_crop.fraction == pytest.approx(0.3)


def test_cdl_aggregation_emits_unknown_below_coverage_threshold(tmp_path: Path) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    rows = _cdl_rows()
    rows[1]["area_m2"] = 19.0
    _write_intersections(cdl_path, rows)

    fractions = aggregate_cdl(
        cdl_path,
        _grid_cells(),
        source_year=2024,
        issued_at=ISSUED_AT,
        layer_metadata=_metadata(cdl_path),
    )

    assert len(fractions) == 1
    assert fractions[0].crop_class == "unknown"
    assert fractions[0].fraction == 0.0
    assert fractions[0].coverage_fraction == pytest.approx(0.79)


def test_cdl_aggregation_rejects_crop_fraction_outside_grid_area(tmp_path: Path) -> None:
    cdl_path = tmp_path / "fixture_cdl_intersections.json"
    rows = _cdl_rows()
    rows[1]["area_m2"] = 50.0
    _write_intersections(cdl_path, rows)

    with pytest.raises(ValueError, match="coverage"):
        aggregate_cdl(
            cdl_path,
            _grid_cells(),
            source_year=2024,
            issued_at=ISSUED_AT,
            layer_metadata=_metadata(cdl_path),
        )


def test_cdl_fixture_is_conspicuously_non_scientific() -> None:
    path = Path("examples/outlook/crop_grid.jsonl")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    layer = CdlLayerMetadata(
        source_year=2024,
        layer_version="fixture-2024-edition",
        legend_version="usda-nass-cdl-2024",
        release_at="2025-02-27T00:00:00Z",
        upstream_uri=LEGEND_URL,
        sha256=checksum,
    )

    assert all(row["fixture_non_scientific"] is True for row in rows)
    fractions = aggregate_cdl(
        path,
        _grid_cells(),
        source_year=2024,
        issued_at=ISSUED_AT,
        layer_metadata=layer,
    )
    assert [item.crop_code for item in fractions] == ["1", "36"]
