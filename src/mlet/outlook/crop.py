"""Dated crop-coefficient inputs and crop-weighted potential ETc."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
import math

from mlet.sources.cdl import CdlLayerMetadata, CropFraction


_MIN_KC = 0.0
_MAX_KC = 1.4
_COVERAGE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class CropCoefficientInput:
    """One explicit, dated crop/vegetation-state coefficient for a run input."""

    crop_code: str | None
    crop_class: str
    kc: float
    effective_date: date
    vegetation_state: str
    source_name: str
    source_version: str
    source_available_at: datetime

    def __post_init__(self) -> None:
        _require_crop_key(self.crop_code, self.crop_class)
        _require_kc(self.kc)
        _require_date(self.effective_date, "crop coefficient effective_date")
        _require_text(self.vegetation_state, "crop coefficient vegetation_state")
        _require_text(self.source_name, "crop coefficient source_name")
        _require_text(self.source_version, "crop coefficient source_version")
        object.__setattr__(
            self,
            "source_available_at",
            _require_utc_timestamp(
                self.source_available_at, "crop coefficient source_available_at"
            ),
        )

    def to_record(
        self, *, issued_at: datetime, valid_date: date
    ) -> dict[str, object]:
        """Return manifest-ready provenance for this coefficient input."""
        _validate_coefficient_eligibility(self, issued_at=issued_at, valid_date=valid_date)
        return {
            "crop_code": self.crop_code,
            "crop_class": self.crop_class,
            "kc": self.kc,
            "effective_date": self.effective_date.isoformat(),
            "vegetation_state": self.vegetation_state,
            "source_name": self.source_name,
            "source_version": self.source_version,
            "source_available_at": _format_utc_timestamp(self.source_available_at),
        }


@dataclass(frozen=True)
class CropCoefficientAssignment:
    """CDL fractions paired with the dated coefficients used to calculate ETc."""

    fractions: tuple[CropFraction, ...]
    crop_coefficients: tuple[CropCoefficientInput, ...]
    issued_at: datetime
    valid_date: date

    def __post_init__(self) -> None:
        issue_time = _require_utc_timestamp(self.issued_at, "issued_at")
        target_date = _require_date(self.valid_date, "valid_date")
        for coefficient in self.crop_coefficients:
            if not isinstance(coefficient, CropCoefficientInput):
                raise ValueError("crop_coefficients must contain CropCoefficientInput records")
            _validate_coefficient_eligibility(
                coefficient, issued_at=issue_time, valid_date=target_date
            )
        object.__setattr__(self, "issued_at", issue_time)

    def to_record(self) -> dict[str, object]:
        """Expose all crop terms needed to replay an ETc calculation."""
        return {
            "issued_at": _format_utc_timestamp(self.issued_at),
            "valid_date": self.valid_date.isoformat(),
            "fractions": [
                {
                    "crop_code": fraction.crop_code,
                    "crop_class": fraction.crop_class,
                    "fraction": fraction.fraction,
                    "coverage_fraction": fraction.coverage_fraction,
                    "cdl_year": fraction.source_year,
                    "kc": fraction.kc,
                }
                for fraction in self.fractions
            ],
            "crop_coefficients": [
                coefficient.to_record(
                    issued_at=self.issued_at, valid_date=self.valid_date
                )
                for coefficient in self.crop_coefficients
            ],
        }


def apply_crop_coefficients(
    fractions: Sequence[CropFraction],
    crop_coefficients: Sequence[CropCoefficientInput],
    *,
    issued_at: datetime,
    valid_date: date,
) -> CropCoefficientAssignment:
    """Apply explicit dated coefficients without silently inventing a crop Kc.

    The caller provides the coefficient inputs selected for its valid date.  No
    coefficient is inferred from a CDL code, crop class, or a previous run.
    """
    issue_time = _require_utc_timestamp(issued_at, "issued_at")
    target_date = _require_date(valid_date, "valid_date")
    coefficient_by_crop: dict[tuple[str | None, str], CropCoefficientInput] = {}
    for coefficient in crop_coefficients:
        if not isinstance(coefficient, CropCoefficientInput):
            raise ValueError("crop_coefficients must contain CropCoefficientInput records")
        _validate_coefficient_eligibility(
            coefficient, issued_at=issue_time, valid_date=target_date
        )
        key = (coefficient.crop_code, coefficient.crop_class)
        if key in coefficient_by_crop:
            raise ValueError("crop_coefficients must not repeat a crop code and class")
        coefficient_by_crop[key] = coefficient

    assigned: list[CropFraction] = []
    required_keys: set[tuple[str | None, str]] = set()
    for fraction in fractions:
        _validate_crop_fraction(fraction)
        if fraction.crop_class == "unknown":
            if fraction.kc is not None:
                raise ValueError("unknown crop coverage must not carry a crop coefficient")
            assigned.append(fraction)
            continue
        key = (fraction.crop_code, fraction.crop_class)
        required_keys.add(key)
        coefficient = coefficient_by_crop.get(key)
        if coefficient is None:
            raise ValueError("missing dated crop coefficient for a known crop fraction")
        assigned.append(replace(fraction, kc=coefficient.kc))

    unused = set(coefficient_by_crop) - required_keys
    if unused:
        raise ValueError("crop coefficient input does not match any known crop fraction")
    if not assigned:
        raise ValueError("crop coefficient assignment requires at least one crop fraction")
    return CropCoefficientAssignment(
        fractions=tuple(assigned),
        crop_coefficients=tuple(crop_coefficients),
        issued_at=issue_time,
        valid_date=target_date,
    )


@dataclass(frozen=True)
class PotentialEtcRecord:
    """One coverage-complete, manifest-ready ample-water ETc calculation."""

    grid_id: str
    eto_mm: float
    potential_et_c_mm: float
    coverage_fraction: float
    known_coverage_fraction: float
    source_year: int
    layer_metadata: CdlLayerMetadata

    def to_record(self) -> dict[str, object]:
        """Return every grid and CDL coverage term needed to replay ETc."""
        layer = self.layer_metadata
        return {
            "grid_id": self.grid_id,
            "eto_mm": self.eto_mm,
            "potential_et_c_mm": self.potential_et_c_mm,
            "coverage_fraction": self.coverage_fraction,
            "known_coverage_fraction": self.known_coverage_fraction,
            "coverage_tolerance": _COVERAGE_TOLERANCE,
            "source_year": self.source_year,
            "cdl_layer": {
                "source_year": layer.source_year,
                "layer_version": layer.layer_version,
                "legend_version": layer.legend_version,
                "release_at": layer.release_at,
                "upstream_uri": layer.upstream_uri,
                "sha256": layer.sha256,
            },
        }


def potential_et_c(
    eto_mm: float, fractions: Sequence[CropFraction]
) -> PotentialEtcRecord:
    """Calculate ETc only for one coverage-complete native weather-grid cell.

    The fraction sum must equal the declared CDL coverage within
    ``_COVERAGE_TOLERANCE``.  This deliberately rejects a dropped crop class
    instead of renormalizing a partial cell into a plausible ETc value.
    """
    eto = _require_finite_nonnegative(eto_mm, "eto_mm")
    cell_fractions = tuple(fractions)
    if not cell_fractions:
        raise ValueError("potential ET requires at least one crop fraction")
    for fraction in cell_fractions:
        _validate_crop_fraction(fraction)

    grid_ids = {fraction.grid_id for fraction in cell_fractions}
    if len(grid_ids) != 1:
        raise ValueError("potential ET fractions must belong to one grid_id")
    source_years = {fraction.source_year for fraction in cell_fractions}
    if len(source_years) != 1:
        raise ValueError("potential ET fractions must share one source_year")
    coverage_fraction = cell_fractions[0].coverage_fraction
    if any(
        not math.isclose(
            fraction.coverage_fraction,
            coverage_fraction,
            rel_tol=0.0,
            abs_tol=_COVERAGE_TOLERANCE,
        )
        for fraction in cell_fractions[1:]
    ):
        raise ValueError("potential ET fractions must share one coverage_fraction")
    layer_metadata = {fraction.layer_metadata for fraction in cell_fractions}
    if len(layer_metadata) != 1:
        raise ValueError("potential ET fractions must share identical CDL layer metadata")

    fraction_sum = sum(fraction.fraction for fraction in cell_fractions)
    if not math.isclose(
        fraction_sum,
        coverage_fraction,
        rel_tol=0.0,
        abs_tol=_COVERAGE_TOLERANCE,
    ):
        raise ValueError(
            "potential ET crop fractions must sum to declared coverage within "
            f"{_COVERAGE_TOLERANCE:g}"
        )

    active: list[CropFraction] = []
    for fraction in cell_fractions:
        if fraction.crop_class != "unknown":
            _require_kc(fraction.kc)
            active.append(fraction)
    if not active:
        raise ValueError("potential ET requires known crop coverage")

    covered_fraction = sum(fraction.fraction for fraction in active)
    if covered_fraction <= 0.0:
        raise ValueError("potential ET requires positive known crop coverage")
    weighted_kc = sum(fraction.fraction * float(fraction.kc) for fraction in active)
    return PotentialEtcRecord(
        grid_id=next(iter(grid_ids)),
        eto_mm=eto,
        potential_et_c_mm=eto * weighted_kc / covered_fraction,
        coverage_fraction=coverage_fraction,
        known_coverage_fraction=covered_fraction,
        source_year=next(iter(source_years)),
        layer_metadata=next(iter(layer_metadata)),
    )


def _validate_crop_fraction(fraction: CropFraction) -> None:
    if not isinstance(fraction, CropFraction):
        raise ValueError("fractions must contain CropFraction records")
    _require_text(fraction.grid_id, "CropFraction grid_id")
    _require_crop_key(fraction.crop_code, fraction.crop_class)
    _require_fraction(fraction.fraction, "CropFraction fraction")
    _require_fraction(fraction.coverage_fraction, "CropFraction coverage_fraction")
    if not isinstance(fraction.source_year, int) or isinstance(fraction.source_year, bool):
        raise ValueError("CropFraction source_year must be a recorded integer")
    if fraction.source_year < 1:
        raise ValueError("CropFraction source_year must be positive")


def _validate_coefficient_eligibility(
    coefficient: CropCoefficientInput, *, issued_at: datetime, valid_date: date
) -> None:
    issue_time = _require_utc_timestamp(issued_at, "issued_at")
    target_date = _require_date(valid_date, "valid_date")
    if coefficient.source_available_at > issue_time:
        raise ValueError(
            "crop coefficient source_available_at is later than issued_at"
        )
    if coefficient.effective_date > issue_time.date():
        raise ValueError("crop coefficient effective_date is later than issued_at")
    if coefficient.effective_date > target_date:
        raise ValueError("crop coefficient effective_date is later than valid_date")


def _require_crop_key(crop_code: str | None, crop_class: object) -> None:
    _require_text(crop_class, "crop_class")
    if crop_class == "unknown":
        if crop_code is not None:
            raise ValueError("unknown crop coverage must not declare a crop code")
        return
    if crop_class == "non_crop":
        if crop_code is not None:
            raise ValueError("non-crop coverage must not declare a crop code")
        return
    _require_text(crop_code, "crop_code")


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _require_date(value: object, label: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{label} must be a date")
    return value


def _require_utc_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be an explicit UTC datetime")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC datetime")
    return value.astimezone(timezone.utc)


def _format_utc_timestamp(value: datetime) -> str:
    utc_value = _require_utc_timestamp(value, "timestamp")
    return utc_value.isoformat().replace("+00:00", "Z")


def _require_fraction(value: object, label: str) -> float:
    result = _require_finite_nonnegative(value, label)
    if result > 1.0:
        raise ValueError(f"{label} must be within [0, 1]")
    return result


def _require_kc(value: object) -> float:
    result = _require_finite_nonnegative(value, "crop coefficient")
    if result > _MAX_KC:
        raise ValueError("crop coefficient must be within [0, 1.4]")
    return result


def _require_finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite non-negative number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return result
