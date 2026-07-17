"""Aggregate issue-time-eligible CDL intersections with frozen legend provenance."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlparse


_COVERAGE_THRESHOLD = 0.8
CDL_2024_LEGEND_VERSION = "usda-nass-cdl-2024"
CDL_2024_LEGEND_URL = (
    "https://www.nass.usda.gov/Research_and_Science/Cropland/metadata/"
    "metadata_Cropland-Data-Layer-2024.htm"
)

# The finite 2024 code set is transcribed from the official USDA NASS data
# dictionary at ``CDL_2024_LEGEND_URL``.  It is deliberately not generalized to
# other years: those require an explicit legend review and a new version label.
_CDL_2024_CROP_CODES = frozenset(
    {
        1,
        2,
        3,
        4,
        5,
        6,
        10,
        11,
        12,
        13,
        14,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
        34,
        35,
        36,
        37,
        38,
        39,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        48,
        49,
        50,
        51,
        52,
        53,
        54,
        55,
        56,
        57,
        58,
        59,
        60,
        66,
        67,
        68,
        69,
        70,
        71,
        72,
        74,
        75,
        76,
        77,
        92,
        204,
        205,
        206,
        207,
        208,
        209,
        210,
        211,
        212,
        213,
        214,
        215,
        216,
        217,
        218,
        219,
        220,
        221,
        222,
        223,
        224,
        225,
        226,
        227,
        228,
        229,
        230,
        231,
        232,
        233,
        234,
        235,
        236,
        237,
        238,
        239,
        240,
        241,
        242,
        243,
        244,
        245,
        246,
        247,
        248,
        249,
        250,
        254,
    }
)
_CDL_2024_NON_CROP_CODES = frozenset(
    {
        0,
        61,
        62,
        63,
        64,
        65,
        81,
        82,
        83,
        87,
        88,
        111,
        112,
        121,
        122,
        123,
        124,
        131,
        141,
        142,
        143,
        152,
        176,
        190,
        195,
    }
)
_CDL_2024_ACCEPTED_CODES = _CDL_2024_CROP_CODES | _CDL_2024_NON_CROP_CODES
_UTC_TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{6})?Z"
)


@dataclass(frozen=True)
class GridCell:
    """Native weather-grid cell area used to normalize CDL intersections."""

    grid_id: str
    area_m2: float


@dataclass(frozen=True)
class CdlLayerMetadata:
    """Immutable archived CDL layer evidence used at one historical issue time."""

    source_year: int
    layer_version: str
    legend_version: str
    release_at: str
    upstream_uri: str
    sha256: str

    def __post_init__(self) -> None:
        """Reject malformed provenance before a public layer record exists."""
        validate_cdl_layer_metadata(self)


@dataclass(frozen=True)
class CropFraction:
    """Area-weighted CDL contribution for one native weather-grid cell."""

    grid_id: str
    crop_code: str | None
    crop_class: str
    fraction: float
    coverage_fraction: float
    source_year: int
    confidence_pct: float | None
    layer_metadata: CdlLayerMetadata
    kc: float | None = None

    def __post_init__(self) -> None:
        """Bind each public fraction to structurally valid, matching CDL evidence."""
        validate_cdl_layer_metadata(self.layer_metadata)
        _validate_requested_source_year(self.source_year)
        if self.source_year != self.layer_metadata.source_year:
            raise ValueError("CropFraction source_year must match its CDL layer provenance")


def aggregate_cdl(
    cdl_path: Path,
    grid_cells: Sequence[GridCell],
    source_year: int,
    *,
    issued_at: str,
    layer_metadata: CdlLayerMetadata,
) -> list[CropFraction]:
    """Aggregate a checksum-addressed 2024 CDL intersection table.

    Every row is checked against the same recorded source year before rows are
    scoped to requested weather cells.  The immutable layer's release time must
    already have passed at ``issued_at``; a later annual map therefore cannot be
    silently introduced into a historical outlook.
    """
    issue_time = _parse_utc_timestamp(issued_at, "issued_at")
    _validate_requested_source_year(source_year)
    _validate_layer_metadata(layer_metadata, source_year, issue_time)
    cells = _validate_grid_cells(grid_cells)
    raw_bytes = _read_bytes(Path(cdl_path))
    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if actual_sha256 != layer_metadata.sha256:
        raise ValueError("CDL intersection table checksum does not match layer metadata")
    rows = _load_rows(raw_bytes)
    by_grid: dict[str, list[tuple[str | None, str, float, float]]] = defaultdict(list)
    for row_index, row in enumerate(rows):
        row_source_year = _require_year(row, row_index)
        if row_source_year != source_year:
            raise ValueError(
                "CDL row source_year does not match the explicitly requested source_year"
            )
        grid_id = _require_text(row, "grid_id", row_index)
        if grid_id not in cells:
            continue
        code = _require_2024_legend_code(row, row_index)
        crop_code, crop_class = _classify_crop_code(row, code, row_index)
        area_m2 = _require_number(
            row, "area_m2", row_index, 0.0, float("inf"), strict_minimum=True
        )
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
                    layer_metadata=layer_metadata,
                )
            )
            continue

        grouped: dict[tuple[str | None, str], tuple[float, float]] = {}
        for crop_code, crop_class, area_m2, confidence_pct in samples:
            existing_area, existing_weighted_confidence = grouped.get(
                (crop_code, crop_class), (0.0, 0.0)
            )
            grouped[(crop_code, crop_class)] = (
                existing_area + area_m2,
                existing_weighted_confidence + area_m2 * confidence_pct,
            )
        for (crop_code, crop_class), (area_m2, weighted_confidence) in sorted(
            grouped.items(),
            key=lambda item: (
                item[0][0] is None,
                int(item[0][0]) if item[0][0] is not None else -1,
                item[0][1],
            ),
        ):
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
                    layer_metadata=layer_metadata,
                )
            )
    return fractions


def _validate_requested_source_year(source_year: int) -> None:
    if not isinstance(source_year, int) or isinstance(source_year, bool):
        raise ValueError("source_year must be a recorded integer")
    if source_year != 2024:
        raise ValueError("source_year is unsupported until its official CDL legend is pinned")


def _validate_layer_metadata(
    layer: CdlLayerMetadata, source_year: int, issue_time: datetime
) -> None:
    release_time = validate_cdl_layer_metadata(layer)
    if layer.source_year != source_year:
        raise ValueError("CDL layer metadata source_year must match the requested source_year")
    if release_time > issue_time:
        raise ValueError("CDL layer metadata release_at is later than issued_at")


def validate_cdl_layer_metadata(layer: object) -> datetime:
    """Validate every immutable CDL provenance field and return its release time.

    This is deliberately reusable outside ``aggregate_cdl``: public crop and
    output records must reject forged or post-construction-mutated metadata
    before it can enter an outlook artifact.
    """
    if not isinstance(layer, CdlLayerMetadata):
        raise ValueError("layer_metadata must be an immutable CdlLayerMetadata record")
    _validate_requested_source_year(layer.source_year)
    if layer.legend_version != CDL_2024_LEGEND_VERSION:
        raise ValueError("CDL layer metadata legend_version is not a pinned supported legend")
    if not isinstance(layer.layer_version, str) or not layer.layer_version.strip():
        raise ValueError("CDL layer metadata layer_version must be non-empty text")
    release_time = _parse_utc_timestamp(layer.release_at, "CDL layer metadata release_at")
    _require_https_url(layer.upstream_uri, "CDL layer metadata upstream_uri")
    _require_sha256(layer.sha256, "CDL layer metadata checksum")
    return release_time


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


def _read_bytes(path: Path) -> bytes:
    try:
        contents = path.read_bytes()
    except OSError as error:
        raise ValueError(f"cannot read CDL intersection table: {path}") from error
    if not contents.strip():
        raise ValueError("CDL intersection table is empty")
    return contents


def _load_rows(contents: bytes) -> list[Mapping[str, object]]:
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("CDL intersection table must be UTF-8") from error
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        decoded = []
        for line_number, line in enumerate(text.splitlines(), start=1):
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
        raise ValueError(
            f"CDL row {row_index} field source_year must be a recorded positive integer"
        )
    return value


def _require_2024_legend_code(row: Mapping[str, object], row_index: int) -> int:
    value = row.get("crop_code")
    if isinstance(value, bool):
        raise ValueError(f"CDL row {row_index} crop_code must be numeric for the 2024 legend")
    if isinstance(value, int):
        code = value
    elif isinstance(value, str) and value.strip().isdigit():
        code = int(value.strip())
    else:
        raise ValueError(f"CDL row {row_index} crop_code must be numeric for the 2024 legend")
    if code not in _CDL_2024_ACCEPTED_CODES:
        raise ValueError(f"CDL row {row_index} crop_code is not recognized by the 2024 legend")
    return code


def _classify_crop_code(
    row: Mapping[str, object], code: int, row_index: int
) -> tuple[str | None, str]:
    value = row.get("crop_class")
    if code in _CDL_2024_NON_CROP_CODES:
        if value is not None and value != "non_crop":
            raise ValueError(f"CDL row {row_index} non-crop code cannot declare a crop_class")
        return None, "non_crop"
    if value is None:
        return str(code), f"cdl_{code}"
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"CDL row {row_index} field crop_class must be non-empty text")
    return str(code), value.strip()


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


def _parse_utc_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or _UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(
            f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z")
    return parsed.astimezone(timezone.utc)


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")
    return value


def _require_https_url(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an HTTPS URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{label} must be an HTTPS URL")
    return value
