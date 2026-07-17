"""Aggregate explicit CDL-to-weather-grid intersections with provenance."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path


_COVERAGE_THRESHOLD = 0.8


@dataclass(frozen=True)
class GridCell:
    """Native weather-grid cell area used to normalize CDL intersections."""

    grid_id: str
    area_m2: float


@dataclass(frozen=True)
class CropFraction:
    """Area-weighted CDL crop contribution for one native weather-grid cell."""

    grid_id: str
    crop_code: str | None
    crop_class: str
    fraction: float
    coverage_fraction: float
    source_year: int
    confidence_pct: float | None
    kc: float | None = None


def aggregate_cdl(
    cdl_path: Path, grid_cells: Sequence[GridCell], source_year: int
) -> list[CropFraction]:
    """Aggregate a reproducible CDL intersection table by native weather cell.

    ``cdl_path`` is an archived JSON array or JSONL table created by the
    spatial-intersection acquisition step.  Each row must retain the official
    ``grid_id``, ``crop_code``, intersected ``area_m2``, confidence percentage,
    and explicit ``source_year``.  This function cannot infer a crop layer from
    a later release: every input row must exactly match ``source_year``.
    """
    if not isinstance(source_year, int) or isinstance(source_year, bool) or source_year < 1:
        raise ValueError("source_year must be a positive recorded integer")
    cells = _validate_grid_cells(grid_cells)
    rows = _load_rows(Path(cdl_path))
    by_grid: dict[str, list[tuple[str, str, float, float]]] = defaultdict(list)
    for row_index, row in enumerate(rows):
        grid_id = _require_text(row, "grid_id", row_index)
        if grid_id not in cells:
            continue
        row_source_year = _require_year(row, row_index)
        if row_source_year != source_year:
            raise ValueError(
                "CDL row source_year does not match the explicitly requested source_year"
            )
        crop_code = _require_crop_code(row, row_index)
        crop_class = _optional_crop_class(row, crop_code, row_index)
        area_m2 = _require_number(row, "area_m2", row_index, 0.0, float("inf"), strict_minimum=True)
        confidence_pct = _require_number(row, "confidence", row_index, 0.0, 100.0)
        by_grid[grid_id].append((crop_code, crop_class, area_m2, confidence_pct))

    fractions: list[CropFraction] = []
    for grid_id in sorted(cells):
        cell = cells[grid_id]
        samples = by_grid.get(grid_id, [])
        covered_area_m2 = sum(sample[2] for sample in samples)
        coverage_fraction = covered_area_m2 / cell.area_m2
        if coverage_fraction > 1.0 + 1e-12:
            raise ValueError(f"CDL coverage exceeds the grid area for {grid_id!r}")
        coverage_fraction = min(1.0, coverage_fraction)
        mean_confidence = (
            sum(area * confidence for _, _, area, confidence in samples) / covered_area_m2
            if covered_area_m2 > 0
            else None
        )
        if coverage_fraction < _COVERAGE_THRESHOLD:
            fractions.append(
                CropFraction(
                    grid_id=grid_id,
                    crop_code=None,
                    crop_class="unknown",
                    fraction=0.0,
                    coverage_fraction=coverage_fraction,
                    source_year=source_year,
                    confidence_pct=mean_confidence,
                )
            )
            continue

        grouped: dict[tuple[str, str], tuple[float, float]] = {}
        for crop_code, crop_class, area_m2, confidence_pct in samples:
            existing_area, existing_weighted_confidence = grouped.get(
                (crop_code, crop_class), (0.0, 0.0)
            )
            grouped[(crop_code, crop_class)] = (
                existing_area + area_m2,
                existing_weighted_confidence + area_m2 * confidence_pct,
            )
        for (crop_code, crop_class), (area_m2, weighted_confidence) in sorted(grouped.items()):
            fraction = area_m2 / cell.area_m2
            if not 0.0 <= fraction <= 1.0:
                raise ValueError("CDL crop fraction must be within [0, 1]")
            fractions.append(
                CropFraction(
                    grid_id=grid_id,
                    crop_code=crop_code,
                    crop_class=crop_class,
                    fraction=fraction,
                    coverage_fraction=coverage_fraction,
                    source_year=source_year,
                    confidence_pct=weighted_confidence / area_m2,
                )
            )
    return fractions


def _validate_grid_cells(grid_cells: Sequence[GridCell]) -> dict[str, GridCell]:
    cells: dict[str, GridCell] = {}
    for cell in grid_cells:
        if not isinstance(cell, GridCell):
            raise ValueError("grid_cells must contain GridCell records")
        if not isinstance(cell.grid_id, str) or not cell.grid_id.strip():
            raise ValueError("GridCell grid_id must be non-empty text")
        if cell.grid_id in cells:
            raise ValueError("grid_cells must not contain duplicate grid_id values")
        area_m2 = _finite_float(cell.area_m2, "GridCell area_m2")
        if area_m2 <= 0:
            raise ValueError("GridCell area_m2 must be positive")
        cells[cell.grid_id] = GridCell(grid_id=cell.grid_id, area_m2=area_m2)
    if not cells:
        raise ValueError("grid_cells must not be empty")
    return cells


def _load_rows(path: Path) -> list[Mapping[str, object]]:
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read CDL intersection table: {path}") from error
    if not contents.strip():
        raise ValueError("CDL intersection table is empty")
    try:
        decoded = json.loads(contents)
    except json.JSONDecodeError:
        decoded = []
        for line_number, line in enumerate(contents.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                decoded.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"CDL JSONL line {line_number} is invalid") from error
    if not isinstance(decoded, list) or any(not isinstance(row, dict) for row in decoded):
        raise ValueError("CDL intersection table must be a JSON array or JSONL objects")
    return decoded


def _require_text(row: Mapping[str, object], name: str, row_index: int) -> str:
    value = row.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"CDL row {row_index} field {name} must be non-empty text")
    return value.strip()


def _require_year(row: Mapping[str, object], row_index: int) -> int:
    value = row.get("source_year")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"CDL row {row_index} field source_year must be a recorded positive integer")
    return value


def _require_crop_code(row: Mapping[str, object], row_index: int) -> str:
    value = row.get("crop_code")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"CDL row {row_index} field crop_code must be text or an integer")
    result = str(value).strip()
    if not result:
        raise ValueError(f"CDL row {row_index} field crop_code must be non-empty")
    return result


def _optional_crop_class(row: Mapping[str, object], crop_code: str, row_index: int) -> str:
    value = row.get("crop_class")
    if value is None:
        return f"cdl_{crop_code}"
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"CDL row {row_index} field crop_class must be non-empty text")
    return value.strip()


def _require_number(
    row: Mapping[str, object],
    name: str,
    row_index: int,
    minimum: float,
    maximum: float,
    *,
    strict_minimum: bool = False,
) -> float:
    value = _finite_float(row.get(name), f"CDL row {row_index} field {name}")
    if value > maximum or value < minimum or (strict_minimum and value == minimum):
        raise ValueError(f"CDL row {row_index} field {name} is outside its allowed range")
    return value


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result
