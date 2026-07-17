"""Software-only checks for explicitly conditional regional ETa scenarios."""

from __future__ import annotations

from datetime import date

import pytest

from mlet.outlook.scenarios import (
    project_no_irrigation,
    project_no_irrigation_from_state,
    project_well_watered,
)
from mlet.outlook.state import (
    StateProvenance,
    eta_analysis_from_openet,
    initialize_no_irrigation_state,
)


def _provenance() -> StateProvenance:
    return StateProvenance(
        source_name="fixture-soil-water-model",
        source_version="fixture-v1",
        source_uri="https://example.test/soil-water",
        observed_date=date(2026, 7, 16),
    )


def test_well_watered_eta_equals_potential_et_with_no_farmer_behavior_claim() -> None:
    output = project_well_watered(5.4, precip_mm=1.2)

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
            "source_uri": "https://example.test/soil-water",
            "source_version": "fixture-v1",
        },
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
    )

    assert 0.0 <= output.ks <= 1.0
    assert output.eta_mm == pytest.approx(0.0)


def test_missing_openet_state_remains_missing_instead_of_becoming_an_analysis() -> None:
    analysis = eta_analysis_from_openet(None)

    assert analysis.eta_analysis_mm is None
    assert analysis.eta_analysis_date is None
    assert analysis.to_record() == {
        "eta_analysis_date": None,
        "eta_analysis_mm": None,
        "source_available_at": None,
        "source_model": None,
        "source_model_version": None,
    }


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
    )

    output = project_no_irrigation_from_state(
        state, potential_et_mm=5.4, precip_mm=0.0
    )

    assert state.is_available is False
    assert output.eta_mm is None
    assert output.to_record()["availability"] == "unavailable"
    assert output.to_record()["scenario"] == "no_irrigation"
    assert output.to_record()["state_provenance"] == _provenance().to_record()


def test_no_irrigation_state_with_recorded_provenance_replays_the_same_recurrence() -> None:
    state = initialize_no_irrigation_state(
        grid_id="fixture-idaho-grid",
        taw_mm=80.0,
        raw_mm=40.0,
        initial_depletion_mm=75.0,
        provenance=_provenance(),
    )

    output = project_no_irrigation_from_state(
        state, potential_et_mm=5.4, precip_mm=0.0
    )

    assert output.eta_mm == pytest.approx(0.675)
    assert output.to_record()["state_provenance"] == _provenance().to_record()


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
        )
