"""Software-only checks for dated crop coefficients and potential ETc."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

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
    coverage_fraction: float = 1.0,
    grid_id: str = "fixture-idaho-grid",
    kc: float | None = None,
) -> CropFraction:
    return CropFraction(
        grid_id=grid_id,
        crop_code=crop_code,
        crop_class=crop_class,
        fraction=fraction,
        coverage_fraction=coverage_fraction,
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


_ISSUED_AT = datetime(2026, 7, 17, tzinfo=timezone.utc)
_VALID_DATE = date(2026, 7, 18)


def test_potential_et_is_coverage_weighted_over_known_crop_fractions() -> None:
    fractions = [
        _fraction(crop_code="1", crop_class="corn", fraction=0.6, kc=1.0),
        _fraction(crop_code=None, crop_class="non_crop", fraction=0.4, kc=0.0),
        _fraction(crop_code=None, crop_class="unknown", fraction=0.0, kc=None),
    ]

    result = potential_et_c(5.0, fractions)

    assert result.potential_et_c_mm == pytest.approx(3.0)
    assert result.to_record() == {
        "cdl_layer": {
            "layer_version": "fixture-2024",
            "legend_version": "usda-nass-cdl-2024",
            "release_at": "2025-02-27T00:00:00Z",
            "sha256": "a" * 64,
            "source_year": 2024,
            "upstream_uri": "https://example.test/cdl",
        },
        "coverage_fraction": 1.0,
        "coverage_tolerance": 1e-9,
        "eto_mm": 5.0,
        "grid_id": "fixture-idaho-grid",
        "known_coverage_fraction": 1.0,
        "potential_et_c_mm": 3.0,
        "source_year": 2024,
    }


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
        source_available_at=datetime(2026, 7, 16, 12, tzinfo=timezone.utc),
    )

    assignment = apply_crop_coefficients(
        [source_fraction], [coefficient], issued_at=_ISSUED_AT, valid_date=_VALID_DATE
    )

    assert assignment.fractions[0].kc == pytest.approx(1.05)
    assert assignment.to_record() == {
        "issued_at": "2026-07-17T00:00:00Z",
        "valid_date": "2026-07-18",
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
                "source_available_at": "2026-07-16T12:00:00Z",
                "source_version": "fixture-v1",
                "vegetation_state": "mid-season",
            }
        ],
    }


def test_dated_crop_coefficient_assignment_never_defaults_a_missing_crop() -> None:
    source_fraction = _fraction(kc=None)

    with pytest.raises(ValueError, match="missing dated crop coefficient"):
        apply_crop_coefficients(
            [source_fraction], [], issued_at=_ISSUED_AT, valid_date=_VALID_DATE
        )


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
        source_available_at=datetime(2026, 7, 16, 12, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="missing dated crop coefficient"):
        apply_crop_coefficients(
            [source_fraction], [coefficient], issued_at=_ISSUED_AT, valid_date=_VALID_DATE
        )


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
        source_available_at=datetime(2026, 7, 16, 12, tzinfo=timezone.utc),
    )

    assignment = apply_crop_coefficients(
        [source_fraction], [coefficient], issued_at=_ISSUED_AT, valid_date=_VALID_DATE
    )

    assert source_fraction.kc is None
    assert assignment.fractions[0] == replace(source_fraction, kc=1.05)


def test_potential_et_rejects_mixed_grid_fractions() -> None:
    with pytest.raises(ValueError, match="one grid_id"):
        potential_et_c(
            5.0,
            [
                _fraction(fraction=0.5, kc=1.0),
                _fraction(
                    crop_code=None,
                    crop_class="non_crop",
                    fraction=0.5,
                    kc=0.0,
                    grid_id="other-idaho-grid",
                ),
            ],
        )


def test_potential_et_rejects_incomplete_fraction_sum_instead_of_renormalizing() -> None:
    with pytest.raises(ValueError, match="sum to declared coverage"):
        potential_et_c(5.0, [_fraction(fraction=0.6, kc=1.0)])


def test_potential_et_rejects_inconsistent_declared_coverage() -> None:
    with pytest.raises(ValueError, match="one coverage_fraction"):
        potential_et_c(
            5.0,
            [
                _fraction(fraction=0.5, coverage_fraction=1.0, kc=1.0),
                _fraction(
                    crop_code=None,
                    crop_class="non_crop",
                    fraction=0.5,
                    coverage_fraction=0.9,
                    kc=0.0,
                ),
            ],
        )


def test_potential_et_rejects_mixed_cdl_source_years() -> None:
    first = _fraction(fraction=0.5, kc=1.0)
    second = replace(
        _fraction(
            crop_code=None,
            crop_class="non_crop",
            fraction=0.5,
            kc=0.0,
        ),
        source_year=2023,
    )

    with pytest.raises(ValueError, match="one source_year"):
        potential_et_c(5.0, [first, second])


def test_crop_coefficient_assignment_rejects_post_issue_source_input() -> None:
    coefficient = CropCoefficientInput(
        crop_code="1",
        crop_class="corn",
        kc=1.05,
        effective_date=date(2026, 7, 16),
        vegetation_state="mid-season",
        source_name="fixture-coefficient-table",
        source_version="fixture-v1",
        source_available_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="source_available_at is later"):
        apply_crop_coefficients(
            [_fraction(kc=None)],
            [coefficient],
            issued_at=_ISSUED_AT,
            valid_date=_VALID_DATE,
        )


def test_crop_coefficient_requires_explicit_utc_source_availability() -> None:
    with pytest.raises(ValueError, match="explicit UTC"):
        CropCoefficientInput(
            crop_code="1",
            crop_class="corn",
            kc=1.05,
            effective_date=date(2026, 7, 16),
            vegetation_state="mid-season",
            source_name="fixture-coefficient-table",
            source_version="fixture-v1",
            source_available_at=datetime(2026, 7, 16, 12),
        )


def test_crop_coefficient_assignment_rejects_future_effective_date() -> None:
    coefficient = CropCoefficientInput(
        crop_code="1",
        crop_class="corn",
        kc=1.05,
        effective_date=date(2099, 1, 1),
        vegetation_state="mid-season",
        source_name="fixture-coefficient-table",
        source_version="fixture-v1",
        source_available_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="effective_date is later than issued_at"):
        apply_crop_coefficients(
            [_fraction(kc=None)],
            [coefficient],
            issued_at=_ISSUED_AT,
            valid_date=_VALID_DATE,
        )


def test_crop_coefficient_assignment_requires_coefficient_effective_on_valid_date() -> None:
    coefficient = CropCoefficientInput(
        crop_code="1",
        crop_class="corn",
        kc=1.05,
        effective_date=date(2026, 7, 17),
        vegetation_state="mid-season",
        source_name="fixture-coefficient-table",
        source_version="fixture-v1",
        source_available_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="effective_date is later than valid_date"):
        apply_crop_coefficients(
            [_fraction(kc=None)],
            [coefficient],
            issued_at=_ISSUED_AT,
            valid_date=date(2026, 7, 16),
        )
