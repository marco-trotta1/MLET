"""Software-only checks for dated crop coefficients and potential ETc."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from mlet.outlook.crop import (
    CropCoefficientAssignment,
    CropCoefficientInput,
    PotentialEtcRecord,
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


def _coefficient(
    *, crop_code: str | None = "1", crop_class: str = "corn", kc: float = 1.0
) -> CropCoefficientInput:
    return CropCoefficientInput(
        crop_code=crop_code,
        crop_class=crop_class,
        kc=kc,
        effective_date=date(2026, 7, 17),
        vegetation_state="fixture-vegetation-state",
        source_name="fixture-coefficient-table",
        source_version="fixture-v1",
        source_available_at=datetime(2026, 7, 16, 12, tzinfo=timezone.utc),
    )


def _assignment(*fractions: CropFraction) -> CropCoefficientAssignment:
    return CropCoefficientAssignment(
        fractions=fractions,
        crop_coefficients=tuple(
            _coefficient(
                crop_code=fraction.crop_code,
                crop_class=fraction.crop_class,
                kc=float(fraction.kc),
            )
            for fraction in fractions
            if fraction.crop_class != "unknown"
        ),
        issued_at=_ISSUED_AT,
        valid_date=_VALID_DATE,
    )


def test_potential_et_is_coverage_weighted_over_known_crop_fractions() -> None:
    fractions = [
        _fraction(crop_code="1", crop_class="corn", fraction=0.6, kc=1.0),
        _fraction(crop_code=None, crop_class="non_crop", fraction=0.4, kc=0.0),
        _fraction(crop_code=None, crop_class="unknown", fraction=0.0, kc=None),
    ]

    assignment = _assignment(*fractions)
    result = potential_et_c(5.0, assignment)

    assert result.potential_et_c_mm == pytest.approx(3.0)
    record = result.to_record()
    assert record["crop_coefficient_assignment"] == assignment.to_record()
    assert {
        key: value for key, value in record.items() if key != "crop_coefficient_assignment"
    } == {
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


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("grid_id", "forged-idaho-grid", "grid_id must match"),
        ("eto_mm", -0.1, "eto_mm"),
        ("potential_et_c_mm", 4.0, "potential_et_c_mm"),
        ("coverage_fraction", 0.5, "coverage_fraction must match"),
        ("known_coverage_fraction", 0.5, "known_coverage_fraction must match"),
        ("source_year", 2023, "source_year must match"),
        (
            "layer_metadata",
            CdlLayerMetadata(
                source_year=2024,
                layer_version="forged-layer",
                legend_version="usda-nass-cdl-2024",
                release_at="2025-02-27T00:00:00Z",
                upstream_uri="https://example.test/cdl",
                sha256="b" * 64,
            ),
            "layer_metadata must match",
        ),
    ),
)
def test_direct_potential_etc_record_rejects_forged_replay_terms(
    field: str, value: object, message: str
) -> None:
    valid_record = potential_et_c(5.0, _assignment(_fraction(kc=1.0)))

    with pytest.raises(ValueError, match=message):
        replace(valid_record, **{field: value})


def test_direct_potential_etc_record_serialization_revalidates_forged_terms() -> None:
    valid_record = potential_et_c(5.0, _assignment(_fraction(kc=1.0)))
    record = PotentialEtcRecord(
        grid_id=valid_record.grid_id,
        eto_mm=valid_record.eto_mm,
        potential_et_c_mm=valid_record.potential_et_c_mm,
        coverage_fraction=valid_record.coverage_fraction,
        known_coverage_fraction=valid_record.known_coverage_fraction,
        source_year=valid_record.source_year,
        layer_metadata=valid_record.layer_metadata,
        crop_coefficient_assignment=valid_record.crop_coefficient_assignment,
    )
    object.__setattr__(record, "potential_et_c_mm", 4.0)

    with pytest.raises(ValueError, match="potential_et_c_mm"):
        record.to_record()


def test_potential_et_rejects_unknown_coverage_without_a_dated_coefficient() -> None:
    with pytest.raises(ValueError, match="known crop coverage"):
        potential_et_c(
            5.0,
            _assignment(_fraction(crop_code=None, crop_class="unknown", kc=None)),
        )


@pytest.mark.parametrize("kc", (None, -0.01, 1.41))
def test_potential_et_rejects_missing_or_out_of_range_coefficients(kc: float | None) -> None:
    with pytest.raises(ValueError, match="crop coefficient"):
        CropCoefficientAssignment(
            fractions=(_fraction(kc=kc),),
            crop_coefficients=(_coefficient(kc=1.0),),
            issued_at=_ISSUED_AT,
            valid_date=_VALID_DATE,
        )


def test_potential_et_rejects_arbitrary_crop_fractions() -> None:
    with pytest.raises(ValueError, match="CropCoefficientAssignment"):
        potential_et_c(5.0, [_fraction(kc=1.0)])  # type: ignore[arg-type]


def test_direct_assignment_rejects_a_fraction_kc_that_does_not_match_its_source() -> None:
    with pytest.raises(ValueError, match="does not match its dated crop coefficient"):
        CropCoefficientAssignment(
            fractions=(_fraction(kc=1.0),),
            crop_coefficients=(_coefficient(kc=1.05),),
            issued_at=_ISSUED_AT,
            valid_date=_VALID_DATE,
        )


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
            _assignment(
                _fraction(fraction=0.5, kc=1.0),
                _fraction(
                    crop_code=None,
                    crop_class="non_crop",
                    fraction=0.5,
                    kc=0.0,
                    grid_id="other-idaho-grid",
                ),
            ),
        )


def test_potential_et_rejects_incomplete_fraction_sum_instead_of_renormalizing() -> None:
    with pytest.raises(ValueError, match="sum to declared coverage"):
        potential_et_c(5.0, _assignment(_fraction(fraction=0.6, kc=1.0)))


def test_potential_et_rejects_inconsistent_declared_coverage() -> None:
    with pytest.raises(ValueError, match="one coverage_fraction"):
        potential_et_c(
            5.0,
            _assignment(
                _fraction(fraction=0.5, coverage_fraction=1.0, kc=1.0),
                _fraction(
                    crop_code=None,
                    crop_class="non_crop",
                    fraction=0.5,
                    coverage_fraction=0.9,
                    kc=0.0,
                ),
            ),
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
        layer_metadata=replace(
            _fraction().layer_metadata,
            source_year=2023,
        ),
    )

    with pytest.raises(ValueError, match="one source_year"):
        potential_et_c(5.0, _assignment(first, second))


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
