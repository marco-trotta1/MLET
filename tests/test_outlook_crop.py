"""Software-only checks for dated crop coefficients and potential ETc."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from mlet.outlook.crop import (
    CropCoefficientInput,
    apply_crop_coefficients,
    potential_et_c,
)
from mlet.sources.cdl import CdlLayerMetadata, CropFraction


def _fraction(
    *,
    crop_code: str | None = "1",
    crop_class: str = "corn",
    fraction: float = 1.0,
    kc: float | None = None,
) -> CropFraction:
    return CropFraction(
        grid_id="fixture-idaho-grid",
        crop_code=crop_code,
        crop_class=crop_class,
        fraction=fraction,
        coverage_fraction=1.0,
        source_year=2024,
        confidence_pct=90.0,
        layer_metadata=CdlLayerMetadata(
            source_year=2024,
            layer_version="fixture-2024",
            legend_version="usda-nass-cdl-2024",
            release_at="2025-02-27T00:00:00Z",
            upstream_uri="https://example.test/cdl",
            sha256="a" * 64,
        ),
        kc=kc,
    )


def test_potential_et_is_coverage_weighted_over_known_crop_fractions() -> None:
    fractions = [
        _fraction(crop_code="1", crop_class="corn", fraction=0.6, kc=1.0),
        _fraction(crop_code=None, crop_class="non_crop", fraction=0.4, kc=0.0),
        _fraction(crop_code=None, crop_class="unknown", fraction=0.0, kc=None),
    ]

    assert potential_et_c(5.0, fractions) == pytest.approx(3.0)


def test_potential_et_rejects_unknown_coverage_without_a_dated_coefficient() -> None:
    with pytest.raises(ValueError, match="known crop coverage"):
        potential_et_c(5.0, [_fraction(crop_code=None, crop_class="unknown", kc=None)])


@pytest.mark.parametrize("kc", (None, -0.01, 1.41))
def test_potential_et_rejects_missing_or_out_of_range_coefficients(kc: float | None) -> None:
    with pytest.raises(ValueError, match="crop coefficient"):
        potential_et_c(5.0, [_fraction(kc=kc)])


def test_dated_crop_coefficient_assignment_retains_replay_metadata() -> None:
    source_fraction = _fraction(kc=None)
    coefficient = CropCoefficientInput(
        crop_code="1",
        crop_class="corn",
        kc=1.05,
        effective_date=date(2026, 7, 17),
        vegetation_state="mid-season",
        source_name="fixture-coefficient-table",
        source_version="fixture-v1",
    )

    assignment = apply_crop_coefficients([source_fraction], [coefficient])

    assert assignment.fractions[0].kc == pytest.approx(1.05)
    assert assignment.to_record() == {
        "fractions": [
            {
                "cdl_year": 2024,
                "coverage_fraction": 1.0,
                "crop_class": "corn",
                "crop_code": "1",
                "fraction": 1.0,
                "kc": 1.05,
            }
        ],
        "crop_coefficients": [
            {
                "crop_class": "corn",
                "crop_code": "1",
                "effective_date": "2026-07-17",
                "kc": 1.05,
                "source_name": "fixture-coefficient-table",
                "source_version": "fixture-v1",
                "vegetation_state": "mid-season",
            }
        ],
    }


def test_dated_crop_coefficient_assignment_never_defaults_a_missing_crop() -> None:
    source_fraction = _fraction(kc=None)

    with pytest.raises(ValueError, match="missing dated crop coefficient"):
        apply_crop_coefficients([source_fraction], [])


def test_dated_crop_coefficient_assignment_rejects_a_mismatched_crop_class() -> None:
    source_fraction = _fraction(kc=None)
    coefficient = CropCoefficientInput(
        crop_code="1",
        crop_class="alfalfa",
        kc=1.05,
        effective_date=date(2026, 7, 17),
        vegetation_state="mid-season",
        source_name="fixture-coefficient-table",
        source_version="fixture-v1",
    )

    with pytest.raises(ValueError, match="missing dated crop coefficient"):
        apply_crop_coefficients([source_fraction], [coefficient])


def test_crop_fraction_input_is_not_mutated_when_a_coefficient_is_applied() -> None:
    source_fraction = _fraction(kc=None)
    coefficient = CropCoefficientInput(
        crop_code="1",
        crop_class="corn",
        kc=1.05,
        effective_date=date(2026, 7, 17),
        vegetation_state="mid-season",
        source_name="fixture-coefficient-table",
        source_version="fixture-v1",
    )

    assignment = apply_crop_coefficients([source_fraction], [coefficient])

    assert source_fraction.kc is None
    assert assignment.fractions[0] == replace(source_fraction, kc=1.05)
