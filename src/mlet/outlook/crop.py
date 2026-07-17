"""Dated crop-coefficient inputs and crop-weighted potential ETc."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
import math

from mlet.sources.cdl import CropFraction


_MIN_KC = 0.0
_MAX_KC = 1.4


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

    def __post_init__(self) -> None:
        _require_crop_key(self.crop_code, self.crop_class)
        _require_kc(self.kc)
        if not isinstance(self.effective_date, date):
            raise ValueError("crop coefficient effective_date must be a date")
        _require_text(self.vegetation_state, "crop coefficient vegetation_state")
        _require_text(self.source_name, "crop coefficient source_name")
        _require_text(self.source_version, "crop coefficient source_version")

    def to_record(self) -> dict[str, object]:
        """Return manifest-ready provenance for this coefficient input."""
        return {
            "crop_code": self.crop_code,
            "crop_class": self.crop_class,
            "kc": self.kc,
            "effective_date": self.effective_date.isoformat(),
            "vegetation_state": self.vegetation_state,
            "source_name": self.source_name,
            "source_version": self.source_version,
        }


@dataclass(frozen=True)
class CropCoefficientAssignment:
    """CDL fractions paired with the dated coefficients used to calculate ETc."""

    fractions: tuple[CropFraction, ...]
    crop_coefficients: tuple[CropCoefficientInput, ...]

    def to_record(self) -> dict[str, object]:
        """Expose all crop terms needed to replay an ETc calculation."""
        return {
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
                coefficient.to_record() for coefficient in self.crop_coefficients
            ],
        }


def apply_crop_coefficients(
    fractions: Sequence[CropFraction],
    crop_coefficients: Sequence[CropCoefficientInput],
) -> CropCoefficientAssignment:
    """Apply explicit dated coefficients without silently inventing a crop Kc.

    The caller provides the coefficient inputs selected for its valid date.  No
    coefficient is inferred from a CDL code, crop class, or a previous run.
    """
    coefficient_by_crop: dict[tuple[str | None, str], CropCoefficientInput] = {}
    for coefficient in crop_coefficients:
        if not isinstance(coefficient, CropCoefficientInput):
            raise ValueError("crop_coefficients must contain CropCoefficientInput records")
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
    )


def potential_et_c(eto_mm: float, fractions: Sequence[CropFraction]) -> float:
    """Calculate ample-water potential ETc as coverage-weighted ``Kc × ETo``."""
    eto = _require_finite_nonnegative(eto_mm, "eto_mm")
    active: list[CropFraction] = []
    for fraction in fractions:
        _validate_crop_fraction(fraction)
        if fraction.crop_class != "unknown":
            _require_kc(fraction.kc)
            active.append(fraction)
    if not active:
        raise ValueError("potential ET requires known crop coverage")

    covered_fraction = sum(fraction.fraction for fraction in active)
    if covered_fraction <= 0.0:
        raise ValueError("potential ET requires positive known crop coverage")
    weighted_kc = sum(fraction.fraction * float(fraction.kc) for fraction in active)
    return eto * weighted_kc / covered_fraction


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
