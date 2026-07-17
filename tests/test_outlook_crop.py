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


_ISSUED_AT = datetime(2026, 7, 17, 18, tzinfo=timezone.utc)
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


def test_public_potential_etc_validator_cannot_use_a_stale_assignment_snapshot() -> None:
    """A public validation call must bind to the record's current assignment."""
    record = potential_et_c(5.0, _assignment(_fraction(kc=1.0)))
    assignment = record.crop_coefficient_assignment
    stale_snapshot = assignment._validated_snapshot()
    object.__setattr__(
        assignment,
        "fractions",
        (replace(assignment.fractions[0], kc=1.1),),
    )

    with pytest.raises(ValueError, match="does not match its dated crop coefficient"):
        record.assert_valid()
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        record.assert_valid(assignment_snapshot=stale_snapshot)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("field", "delta", "message"),
    (
        ("potential_et_c_mm", 1e-12, "potential_et_c_mm"),
        ("coverage_fraction", 1e-12, "coverage_fraction"),
        ("known_coverage_fraction", 1e-12, "known_coverage_fraction"),
    ),
)
def test_direct_potential_etc_record_rejects_even_small_noncanonical_terms(
    field: str, delta: float, message: str
) -> None:
    valid_record = potential_et_c(
        5.0,
        _assignment(
            _fraction(
                crop_code="1",
                crop_class="corn",
                fraction=0.6,
                coverage_fraction=0.9,
                kc=1.0,
            ),
            _fraction(
                crop_code=None,
                crop_class="non_crop",
                fraction=0.3,
                coverage_fraction=0.9,
                kc=0.0,
            ),
        ),
    )

    with pytest.raises(ValueError, match=message):
        replace(valid_record, **{field: getattr(valid_record, field) + delta})


def test_crop_assignment_revalidates_mutated_cdl_metadata() -> None:
    fraction = _fraction(kc=1.0)
    object.__setattr__(fraction.layer_metadata, "sha256", "A" * 64)

    with pytest.raises(ValueError, match="lowercase SHA-256"):
        _assignment(fraction)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("vegetation_state", " ", "vegetation_state"),
        ("source_name", "", "source_name"),
        ("source_version", "", "source_version"),
        ("effective_date", datetime(2026, 7, 17, tzinfo=timezone.utc), "effective_date"),
        ("source_available_at", datetime(2026, 7, 16, 12), "explicit UTC"),
    ),
)
def test_crop_coefficient_assignment_rejects_post_construction_structural_bypasses(
    field: str, value: object, message: str
) -> None:
    coefficient = _coefficient()
    object.__setattr__(coefficient, field, value)

    with pytest.raises(ValueError, match=message):
        CropCoefficientAssignment(
            fractions=(_fraction(kc=1.0),),
            crop_coefficients=(coefficient,),
            issued_at=_ISSUED_AT,
            valid_date=_VALID_DATE,
        )


def test_crop_coefficient_serialization_revalidates_a_mutated_source_identity() -> None:
    assignment = _assignment(_fraction(kc=1.0))
    object.__setattr__(assignment.crop_coefficients[0], "source_name", "")

    with pytest.raises(ValueError, match="source_name"):
        assignment.to_record()


@pytest.mark.parametrize("field", ("fractions", "crop_coefficients"))
def test_crop_assignment_serialization_uses_its_validated_iterator_snapshot(
    field: str,
) -> None:
    assignment = _assignment(_fraction(kc=1.0))
    expected_record = assignment.to_record()
    original_inputs = getattr(assignment, field)
    object.__setattr__(
        assignment, field, (item for item in original_inputs)
    )

    assert assignment.to_record() == expected_record


@pytest.mark.parametrize("field", ("fractions", "crop_coefficients"))
def test_potential_etc_serialization_uses_its_validated_iterator_snapshot(
    field: str,
) -> None:
    result = potential_et_c(5.0, _assignment(_fraction(kc=1.0)))
    expected_record = result.to_record()
    assignment = result.crop_coefficient_assignment
    original_inputs = getattr(assignment, field)
    object.__setattr__(
        assignment, field, (item for item in original_inputs)
    )

    assert result.to_record() == expected_record


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda fractions: object.__setattr__(fractions[1], "grid_id", "other-grid"),
            "one grid_id",
        ),
        (
            lambda fractions: object.__setattr__(fractions[1], "source_year", 2023),
            "source_year",
        ),
        (
            lambda fractions: object.__setattr__(
                fractions[1],
                "layer_metadata",
                replace(fractions[1].layer_metadata, layer_version="other-layer"),
            ),
            "identical CDL layer metadata",
        ),
        (
            lambda fractions: object.__setattr__(
                fractions[1], "coverage_fraction", 0.5000000005
            ),
            "one coverage_fraction",
        ),
        (
            lambda fractions: object.__setattr__(fractions[1], "fraction", 0.49),
            "sum to declared coverage",
        ),
    ),
)
def test_crop_assignment_serialization_revalidates_native_cell_structure(
    mutation: object, message: str
) -> None:
    assignment = _assignment(
        _fraction(fraction=0.5, coverage_fraction=1.0, kc=1.0),
        _fraction(
            crop_code=None,
            crop_class="non_crop",
            fraction=0.5,
            coverage_fraction=1.0,
            kc=0.0,
        ),
    )

    mutation(assignment.fractions)  # type: ignore[operator]

    with pytest.raises(ValueError, match=message):
        assignment.to_record()


def test_direct_crop_assignment_rejects_mixed_native_cell_structure() -> None:
    with pytest.raises(ValueError, match="one grid_id"):
        CropCoefficientAssignment(
            fractions=(
                _fraction(fraction=0.5, kc=1.0),
                _fraction(
                    crop_code=None,
                    crop_class="non_crop",
                    fraction=0.5,
                    kc=0.0,
                    grid_id="other-grid",
                ),
            ),
            crop_coefficients=(
                _coefficient(),
                _coefficient(crop_code=None, crop_class="non_crop", kc=0.0),
            ),
            issued_at=_ISSUED_AT,
            valid_date=_VALID_DATE,
        )


def test_non_crop_only_assignment_remains_a_serializable_provenance_record() -> None:
    assignment = _assignment(
        _fraction(crop_code=None, crop_class="non_crop", kc=0.0)
    )

    assert assignment.to_record()["fractions"][0]["kc"] == 0.0


def test_non_crop_coefficient_rejects_nonzero_kc() -> None:
    with pytest.raises(ValueError, match="non-crop crop coefficient must equal 0"):
        _coefficient(crop_code=None, crop_class="non_crop", kc=0.1)


def test_non_crop_coefficient_serialization_revalidates_a_mutated_kc() -> None:
    coefficient = _coefficient(crop_code=None, crop_class="non_crop", kc=0.0)
    object.__setattr__(coefficient, "kc", 0.1)

    with pytest.raises(ValueError, match="non-crop crop coefficient must equal 0"):
        coefficient.to_record(issued_at=_ISSUED_AT, valid_date=_VALID_DATE)


def test_crop_assignment_serialization_rejects_a_mutated_non_crop_kc() -> None:
    assignment = _assignment(
        _fraction(crop_code=None, crop_class="non_crop", kc=0.0)
    )
    object.__setattr__(assignment.fractions[0], "kc", 0.1)

    with pytest.raises(ValueError, match="non-crop crop coefficient must equal 0"):
        assignment.to_record()


def test_etc_serialization_rejects_a_mutated_non_crop_kc() -> None:
    result = potential_et_c(
        5.0,
        _assignment(
            _fraction(crop_code="1", crop_class="corn", fraction=0.5, kc=1.0),
            _fraction(
                crop_code=None,
                crop_class="non_crop",
                fraction=0.5,
                kc=0.0,
            ),
        ),
    )
    object.__setattr__(result.crop_coefficient_assignment.fractions[1], "kc", 0.1)

    with pytest.raises(ValueError, match="non-crop crop coefficient must equal 0"):
        result.to_record()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("crop_code", "999", "2024 legend"),
        ("crop_code", "0", "explicit non_crop"),
        ("crop_code", None, "crop_code"),
        ("crop_class", "non_crop", "explicit non_crop"),
        ("fraction", 0.7, "must not exceed coverage_fraction"),
        ("confidence_pct", 101.0, "confidence_pct"),
    ),
)
def test_crop_fraction_rejects_invalid_pinned_legend_semantics_at_construction(
    field: str, value: object, message: str
) -> None:
    fields: dict[str, object] = {
        "grid_id": "fixture-idaho-grid",
        "crop_code": "1",
        "crop_class": "corn",
        "fraction": 0.6,
        "coverage_fraction": 0.6,
        "source_year": 2024,
        "confidence_pct": 90.0,
        "layer_metadata": _fraction().layer_metadata,
    }
    fields[field] = value

    with pytest.raises(ValueError, match=message):
        CropFraction(**fields)  # type: ignore[arg-type]


def test_assignment_and_etc_revalidate_a_mutated_crop_fraction_semantics() -> None:
    fraction = _fraction(kc=None)
    object.__setattr__(fraction, "crop_code", "999")

    with pytest.raises(ValueError, match="2024 legend"):
        apply_crop_coefficients(
            [fraction], [_coefficient()], issued_at=_ISSUED_AT, valid_date=_VALID_DATE
        )

    assignment = _assignment(_fraction(kc=1.0))
    object.__setattr__(assignment.fractions[0], "crop_class", "non_crop")
    with pytest.raises(ValueError, match="explicit non_crop"):
        potential_et_c(5.0, assignment)


def test_etc_serialization_revalidates_a_mutated_crop_fraction_semantics() -> None:
    result = potential_et_c(5.0, _assignment(_fraction(kc=1.0)))
    object.__setattr__(result.crop_coefficient_assignment.fractions[0], "crop_code", "999")

    with pytest.raises(ValueError, match="2024 legend"):
        result.to_record()


def test_potential_etc_serialization_revalidates_mutated_cdl_metadata() -> None:
    record = potential_et_c(5.0, _assignment(_fraction(kc=1.0)))
    object.__setattr__(record.layer_metadata, "upstream_uri", "http://forged.example/cdl")

    with pytest.raises(ValueError, match="HTTPS"):
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
        "issued_at": "2026-07-17T18:00:00Z",
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


def test_potential_et_rejects_even_tiny_declared_coverage_mismatches() -> None:
    with pytest.raises(ValueError, match="one coverage_fraction"):
        potential_et_c(
            5.0,
            _assignment(
                _fraction(fraction=0.3, coverage_fraction=0.5, kc=1.0),
                _fraction(
                    crop_code=None,
                    crop_class="non_crop",
                    fraction=0.2,
                    coverage_fraction=0.5000000005,
                    kc=0.0,
                ),
            ),
        )


def test_potential_et_rejects_mixed_cdl_source_years() -> None:
    first = _fraction(fraction=0.5, kc=1.0)
    second = _fraction(
        crop_code=None,
        crop_class="non_crop",
        fraction=0.5,
        kc=0.0,
    )
    object.__setattr__(second, "source_year", 2023)
    object.__setattr__(second.layer_metadata, "source_year", 2023)

    with pytest.raises(ValueError, match="source_year"):
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

    with pytest.raises(ValueError, match="effective_date is later than the Idaho-local issued_at date"):
        apply_crop_coefficients(
            [_fraction(kc=None)],
            [coefficient],
            issued_at=_ISSUED_AT,
            valid_date=_VALID_DATE,
        )


def test_crop_coefficient_effective_date_uses_idaho_local_issue_day() -> None:
    coefficient = CropCoefficientInput(
        crop_code="1",
        crop_class="corn",
        kc=1.05,
        effective_date=date(2026, 7, 16),
        vegetation_state="mid-season",
        source_name="fixture-coefficient-table",
        source_version="fixture-v1",
        source_available_at=datetime(2026, 7, 15, 12, tzinfo=timezone.utc),
    )
    fractions = [_fraction(kc=None)]

    with pytest.raises(ValueError, match="Idaho-local issued_at date"):
        apply_crop_coefficients(
            fractions,
            [coefficient],
            issued_at=datetime(2026, 7, 16, 0, tzinfo=timezone.utc),
            valid_date=date(2026, 7, 16),
        )

    assignment = apply_crop_coefficients(
        fractions,
        [coefficient],
        issued_at=datetime(2026, 7, 16, 18, tzinfo=timezone.utc),
        valid_date=date(2026, 7, 17),
    )
    assert assignment.issued_at == datetime(2026, 7, 16, 18, tzinfo=timezone.utc)


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
