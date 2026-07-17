"""Software-only checks for explicitly conditional regional ETa scenarios."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from mlet.outlook.scenarios import (
    ScenarioProjection,
    project_no_irrigation,
    project_no_irrigation_from_state,
    project_well_watered,
)
from mlet.outlook.state import (
    EtaAnalysisLayer,
    NoIrrigationState,
    StateProvenance,
    eta_analysis_from_openet,
    initialize_no_irrigation_state,
)


_ISSUED_AT = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _provenance() -> StateProvenance:
    return StateProvenance(
        source_name="fixture-soil-water-model",
        source_version="fixture-v1",
        source_uri="https://example.test/soil-water",
        observed_date=date(2026, 7, 16),
        source_available_at=datetime(2026, 7, 16, 18, tzinfo=timezone.utc),
    )


def _direct_no_irrigation_projection() -> ScenarioProjection:
    """Return a replay-consistent direct construction for boundary checks."""
    return ScenarioProjection(
        scenario="no_irrigation",
        eta_mm=0.675,
        depletion_mm=75.675,
        initial_depletion_mm=75.0,
        taw_mm=80.0,
        raw_mm=40.0,
        ks=0.125,
        potential_et_mm=5.4,
        precip_mm=0.0,
        assumptions=("no_irrigation_after_issue_time",),
        state_provenance=_provenance(),
        issued_at=_ISSUED_AT,
        unavailable_reason=None,
    )


def test_well_watered_eta_equals_potential_et_with_no_farmer_behavior_claim() -> None:
    output = project_well_watered(5.4, precip_mm=1.2, issued_at=_ISSUED_AT)

    assert output.eta_mm == pytest.approx(5.4)
    assert output.ks == pytest.approx(1.0)
    assert output.to_record()["scenario"] == "well_watered"
    assert output.to_record()["assumptions"] == ["crop_water_not_limiting"]
    assert "irrigation" not in output.to_record()


def test_no_irrigation_scenario_never_exceeds_potential_et() -> None:
    output = project_no_irrigation(
        initial_depletion_mm=20.0,
        taw_mm=80.0,
        raw_mm=40.0,
        potential_et_mm=5.4,
        precip_mm=0.0,
        state_provenance=_provenance(),
        issued_at=_ISSUED_AT,
    )

    assert 0.0 <= output.eta_mm <= 5.4
    assert output.depletion_mm > 20.0


def test_no_irrigation_recurrence_persists_every_replay_term_and_scenario_label() -> None:
    output = project_no_irrigation(
        initial_depletion_mm=75.0,
        taw_mm=80.0,
        raw_mm=40.0,
        potential_et_mm=5.4,
        precip_mm=0.0,
        state_provenance=_provenance(),
        issued_at=_ISSUED_AT,
    )

    assert output.ks == pytest.approx(0.125)
    assert output.eta_mm == pytest.approx(0.675)
    assert output.depletion_mm == pytest.approx(75.675)
    assert output.to_record() == {
        "assumptions": ["no_irrigation_after_issue_time"],
        "availability": "available",
        "depletion_mm": 75.675,
        "initial_depletion_mm": 75.0,
        "ks": 0.125,
        "potential_et_mm": 5.4,
        "precip_mm": 0.0,
        "raw_mm": 40.0,
        "scenario": "no_irrigation",
        "state_provenance": {
            "observed_date": "2026-07-16",
            "source_name": "fixture-soil-water-model",
            "source_available_at": "2026-07-16T18:00:00Z",
            "source_uri": "https://example.test/soil-water",
            "source_version": "fixture-v1",
        },
        "issued_at": "2026-07-17T00:00:00Z",
        "taw_mm": 80.0,
        "unavailable_reason": None,
        "eta_mm": 0.675,
    }


def test_rainfall_cannot_create_negative_depletion() -> None:
    output = project_no_irrigation(
        initial_depletion_mm=5.0,
        taw_mm=80.0,
        raw_mm=40.0,
        potential_et_mm=5.4,
        precip_mm=50.0,
        state_provenance=_provenance(),
        issued_at=_ISSUED_AT,
    )

    assert output.depletion_mm == pytest.approx(0.0)


def test_no_irrigation_stress_coefficient_stays_bounded() -> None:
    output = project_no_irrigation(
        initial_depletion_mm=80.0,
        taw_mm=80.0,
        raw_mm=40.0,
        potential_et_mm=5.4,
        precip_mm=0.0,
        state_provenance=_provenance(),
        issued_at=_ISSUED_AT,
    )

    assert 0.0 <= output.ks <= 1.0
    assert output.eta_mm == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("scenario", "actual_et_forecast", "scenario must be exactly"),
        ("potential_et_mm", -0.1, "potential_et_mm"),
        ("precip_mm", float("nan"), "precip_mm"),
        ("eta_mm", 5.5, "eta_mm must not exceed potential_et_mm"),
        ("taw_mm", 0.0, "taw_mm"),
        ("raw_mm", 81.0, "raw_mm must not exceed taw_mm"),
        ("initial_depletion_mm", -0.1, "initial_depletion_mm"),
        ("depletion_mm", 80.1, "depletion_mm"),
        ("ks", 1.1, "ks"),
        ("assumptions", ("crop_water_not_limiting",), "assumptions"),
        ("unavailable_reason", "forged unavailable", "unavailable_reason"),
    ),
)
def test_direct_scenario_projection_rejects_out_of_contract_fields(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_direct_no_irrigation_projection(), **{field: value})


def test_direct_scenario_projection_rejects_forged_recurrence() -> None:
    with pytest.raises(ValueError, match="recurrence"):
        replace(_direct_no_irrigation_projection(), eta_mm=0.5)


def test_direct_scenario_projection_rejects_unavailable_branch_without_reason() -> None:
    with pytest.raises(ValueError, match="unavailable_reason"):
        ScenarioProjection(
            scenario="no_irrigation",
            eta_mm=None,
            depletion_mm=None,
            initial_depletion_mm=None,
            taw_mm=80.0,
            raw_mm=40.0,
            ks=None,
            potential_et_mm=5.4,
            precip_mm=0.0,
            assumptions=("no_irrigation_after_issue_time",),
            state_provenance=_provenance(),
            issued_at=_ISSUED_AT,
            unavailable_reason=None,
        )


def test_scenario_projection_serialization_revalidates_a_forged_record() -> None:
    projection = _direct_no_irrigation_projection()
    object.__setattr__(projection, "eta_mm", 0.5)

    with pytest.raises(ValueError, match="recurrence"):
        projection.to_record()


def test_missing_openet_state_remains_missing_instead_of_becoming_an_analysis() -> None:
    analysis = eta_analysis_from_openet(None, issued_at=_ISSUED_AT)

    assert analysis.eta_analysis_mm is None
    assert analysis.eta_analysis_date is None
    assert analysis.to_record() == {
        "eta_analysis_date": None,
        "eta_analysis_mm": None,
        "source_available_at": None,
        "source_model": None,
        "source_model_version": None,
        "issued_at": "2026-07-17T00:00:00Z",
    }


@pytest.mark.parametrize(
    ("eta_analysis_date", "source_available_at", "message"),
    (
        (date(2026, 7, 17), datetime(2026, 7, 16, 18, tzinfo=timezone.utc), "strictly before"),
        (date(2026, 7, 16), datetime(2026, 7, 18, tzinfo=timezone.utc), "later than issued_at"),
    ),
)
def test_direct_eta_analysis_layer_rejects_ineligible_observations(
    eta_analysis_date: date, source_available_at: datetime, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        EtaAnalysisLayer(
            eta_analysis_mm=4.2,
            eta_analysis_date=eta_analysis_date,
            source_available_at=source_available_at,
            source_model="fixture-openet-model",
            source_model_version="fixture-v1",
            issued_at=_ISSUED_AT,
        )


def test_direct_eta_analysis_layer_serializes_only_an_eligible_completed_day() -> None:
    analysis = EtaAnalysisLayer(
        eta_analysis_mm=4.2,
        eta_analysis_date=date(2026, 7, 16),
        source_available_at=datetime(2026, 7, 16, 18, tzinfo=timezone.utc),
        source_model="fixture-openet-model",
        source_model_version="fixture-v1",
        issued_at=_ISSUED_AT,
    )

    assert analysis.to_record()["eta_analysis_date"] == "2026-07-16"
    assert analysis.to_record()["source_available_at"] == "2026-07-16T18:00:00Z"


@pytest.mark.parametrize(
    ("initial_depletion_mm", "raw_mm", "unavailable_reason", "message"),
    (
        (80.1, 40.0, None, r"within \[0, taw_mm\]"),
        (20.0, 81.0, None, "must not exceed taw_mm"),
        (None, 40.0, None, "unavailable_reason"),
    ),
)
def test_direct_no_irrigation_state_rejects_invalid_or_ambiguous_availability(
    initial_depletion_mm: float | None,
    raw_mm: float,
    unavailable_reason: str | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        NoIrrigationState(
            grid_id="fixture-idaho-grid",
            taw_mm=80.0,
            raw_mm=raw_mm,
            initial_depletion_mm=initial_depletion_mm,
            provenance=_provenance(),
            issued_at=_ISSUED_AT,
            unavailable_reason=unavailable_reason,
        )


def test_direct_no_irrigation_state_serializes_unavailable_only_with_a_reason() -> None:
    state = NoIrrigationState(
        grid_id="fixture-idaho-grid",
        taw_mm=80.0,
        raw_mm=40.0,
        initial_depletion_mm=None,
        provenance=_provenance(),
        issued_at=_ISSUED_AT,
        unavailable_reason="fixture state unavailable",
    )

    assert state.is_available is False
    assert state.to_record()["availability"] == "unavailable"


@pytest.mark.parametrize("initial_depletion_mm", (None, -0.1, 80.1))
def test_no_irrigation_state_without_valid_recorded_depletion_is_unavailable(
    initial_depletion_mm: float | None,
) -> None:
    state = initialize_no_irrigation_state(
        grid_id="fixture-idaho-grid",
        taw_mm=80.0,
        raw_mm=40.0,
        initial_depletion_mm=initial_depletion_mm,
        provenance=_provenance(),
        issued_at=_ISSUED_AT,
    )

    output = project_no_irrigation_from_state(
        state, potential_et_mm=5.4, precip_mm=0.0, issued_at=_ISSUED_AT
    )

    assert state.is_available is False
    assert output.eta_mm is None
    assert output.to_record()["availability"] == "unavailable"
    assert output.to_record()["scenario"] == "no_irrigation"
    assert output.to_record()["state_provenance"] == _provenance().to_record(
        issued_at=_ISSUED_AT
    )


def test_no_irrigation_state_with_recorded_provenance_replays_the_same_recurrence() -> None:
    state = initialize_no_irrigation_state(
        grid_id="fixture-idaho-grid",
        taw_mm=80.0,
        raw_mm=40.0,
        initial_depletion_mm=75.0,
        provenance=_provenance(),
        issued_at=_ISSUED_AT,
    )

    output = project_no_irrigation_from_state(
        state, potential_et_mm=5.4, precip_mm=0.0, issued_at=_ISSUED_AT
    )

    assert output.eta_mm == pytest.approx(0.675)
    assert output.to_record()["state_provenance"] == _provenance().to_record(
        issued_at=_ISSUED_AT
    )


@pytest.mark.parametrize("raw_mm", (0.0, -1.0))
def test_no_irrigation_rejects_nonpositive_raw_water(raw_mm: float) -> None:
    with pytest.raises(ValueError, match="raw_mm must be positive"):
        project_no_irrigation(
            initial_depletion_mm=20.0,
            taw_mm=80.0,
            raw_mm=raw_mm,
            potential_et_mm=5.4,
            precip_mm=0.0,
            state_provenance=_provenance(),
            issued_at=_ISSUED_AT,
        )


def test_state_initialization_rejects_post_issue_source_availability() -> None:
    provenance = StateProvenance(
        source_name="fixture-soil-water-model",
        source_version="fixture-v1",
        source_uri="https://example.test/soil-water",
        observed_date=date(2026, 7, 16),
        source_available_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="source_available_at is later"):
        initialize_no_irrigation_state(
            grid_id="fixture-idaho-grid",
            taw_mm=80.0,
            raw_mm=40.0,
            initial_depletion_mm=20.0,
            provenance=provenance,
            issued_at=_ISSUED_AT,
        )


def test_no_irrigation_projection_rejects_future_observed_state() -> None:
    provenance = StateProvenance(
        source_name="fixture-soil-water-model",
        source_version="fixture-v1",
        source_uri="https://example.test/soil-water",
        observed_date=date(2099, 1, 1),
        source_available_at=datetime(2026, 7, 16, 18, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="observed_date is later"):
        project_no_irrigation(
            initial_depletion_mm=20.0,
            taw_mm=80.0,
            raw_mm=40.0,
            potential_et_mm=5.4,
            precip_mm=0.0,
            state_provenance=provenance,
            issued_at=_ISSUED_AT,
        )


def test_state_provenance_requires_explicit_utc_source_availability() -> None:
    with pytest.raises(ValueError, match="explicit UTC"):
        StateProvenance(
            source_name="fixture-soil-water-model",
            source_version="fixture-v1",
            source_uri="https://example.test/soil-water",
            observed_date=date(2026, 7, 16),
            source_available_at=datetime(2026, 7, 16, 18),
        )
