"""Non-scientific deterministic checks for the FAO-56 dual-coefficient step.

The equivalence test reproduces the vendored pyfao56 daily advance transcribed
from vendor/pyfao56/src/pyfao56/model.py, so agreement is checked against the
same equations pyfao56 implements rather than against this module's own output.
"""

import numpy as np
import pytest

from mlet.hybrid.bounded import FAO56_STRESS_RANGE
from mlet.hybrid.fao56_dual import (
    DailyStep,
    SoilLimits,
    advance_one_day,
    fao56_stress_coefficient,
    readily_available_water,
    run_water_balance,
    total_available_water,
)

LIMITS = SoilLimits(
    theta_fc=0.28, theta_wp=0.13, root_depth_m=1.2, depletion_fraction_p=0.55, units="mm"
)


def _steps() -> tuple[DailyStep, ...]:
    """Ten days with two wetting events and one dry-down.

    The second event is deliberately 100 mm so Eq. 88 has positive excess
    water. The originally drafted 25 mm event never exceeded depletion plus
    ETa, making the partial-percolation assertion mathematically impossible;
    this is a deterministic test-fixture correction, not a production change.
    """
    rain = [0.0, 0.0, 18.0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0]
    return tuple(
        DailyStep(
            eto_mm=7.0,
            kcb=1.05,
            ke=0.12,
            effective_rain_mm=value,
            effective_irrigation_mm=0.0,
        )
        for value in rain
    )


def _pyfao56_reference(initial_depletion_mm: float) -> list[float]:
    """The pyfao56 advance, transcribed from model.py:932-991."""
    taw = 1000.0 * (LIMITS.theta_fc - LIMITS.theta_wp) * LIMITS.root_depth_m
    raw = LIMITS.depletion_fraction_p * taw
    depletion = initial_depletion_mm
    trajectory = []
    for step in _steps():
        ks = sorted([0.0, (taw - depletion) / (taw - raw), 1.0])[1]
        ka = ks * step.kcb + step.ke
        eta = ka * step.eto_mm
        effrain = step.effective_rain_mm
        effirr = step.effective_irrigation_mm
        dp = max([effrain + effirr - eta - depletion, 0.0])
        depletion = sorted([0.0, depletion - effrain - effirr + eta + dp, taw])[1]
        trajectory.append(depletion)
    return trajectory


def test_taw_and_raw_match_equations_82_and_83() -> None:
    expected_taw = 1000.0 * (0.28 - 0.13) * 1.2
    assert total_available_water(LIMITS) == pytest.approx(expected_taw)
    assert readily_available_water(LIMITS) == pytest.approx(0.55 * expected_taw)


def test_stress_coefficient_matches_equation_84_and_saturates() -> None:
    taw = total_available_water(LIMITS)
    raw = readily_available_water(LIMITS)
    # Above RAW there is no stress.
    assert fao56_stress_coefficient(0.0, LIMITS) == pytest.approx(1.0)
    assert fao56_stress_coefficient(raw, LIMITS) == pytest.approx(1.0)
    # At full depletion Ks is zero.
    assert fao56_stress_coefficient(taw, LIMITS) == pytest.approx(0.0)
    # Between RAW and TAW it declines linearly.
    midpoint = 0.5 * (raw + taw)
    assert fao56_stress_coefficient(midpoint, LIMITS) == pytest.approx(
        (taw - midpoint) / (taw - raw)
    )
    # Never leaves [0, 1] even for a depletion beyond TAW.
    assert fao56_stress_coefficient(taw * 2, LIMITS) == pytest.approx(0.0)


def test_default_parameters_reproduce_pyfao56_exactly() -> None:
    """The load-bearing test: with FAO-56 defaults this IS the FAO-56 balance."""
    initial = 40.0
    results = run_water_balance(
        initial,
        _steps(),
        LIMITS,
        ks=None,  # None means "use FAO-56 Eq. 84"
        deep_percolation_fraction=1.0,
    )
    produced = [result.depletion_mm for result in results]
    assert produced == pytest.approx(_pyfao56_reference(initial), rel=0, abs=1e-12)


def test_mass_closes_on_every_unclipped_day() -> None:
    """Dr_new - Dr_old must equal ETa + DP - rain - irrigation."""
    initial = 40.0
    results = run_water_balance(
        initial, _steps(), LIMITS, ks=None, deep_percolation_fraction=1.0
    )
    previous = initial
    for result, step in zip(results, _steps()):
        if result.clipped:
            continue
        expected_change = (
            result.eta_mm
            + result.deep_percolation_mm
            - step.effective_rain_mm
            - step.effective_irrigation_mm
        )
        assert result.depletion_mm - previous == pytest.approx(expected_change, abs=1e-12)
        previous = result.depletion_mm


def test_depletion_never_leaves_physical_bounds() -> None:
    taw = total_available_water(LIMITS)
    for initial in (0.0, 40.0, taw):
        for ks in (0.0, 0.5, 1.0):
            results = run_water_balance(
                initial, _steps(), LIMITS, ks=ks, deep_percolation_fraction=0.5
            )
            depletions = np.array([result.depletion_mm for result in results])
            assert np.all(depletions >= 0.0)
            assert np.all(depletions <= taw)


def test_learned_terms_accept_per_step_arrays() -> None:
    steps = _steps()
    ks_series = np.linspace(0.2, 1.0, len(steps))
    dp_series = np.linspace(0.0, 1.0, len(steps))
    results = run_water_balance(
        40.0, steps, LIMITS, ks=ks_series, deep_percolation_fraction=dp_series
    )
    assert len(results) == len(steps)
    assert [result.ks_used for result in results] == pytest.approx(list(ks_series))


def test_a_lower_percolation_fraction_retains_water() -> None:
    """The physical meaning of the learned drainage term."""
    steps = _steps()
    full_drain = run_water_balance(40.0, steps, LIMITS, ks=None, deep_percolation_fraction=1.0)
    partial_drain = run_water_balance(40.0, steps, LIMITS, ks=None, deep_percolation_fraction=0.2)
    assert partial_drain[-1].depletion_mm <= full_drain[-1].depletion_mm
    assert sum(r.deep_percolation_mm for r in partial_drain) < sum(
        r.deep_percolation_mm for r in full_drain
    )


def test_out_of_range_learned_ks_is_rejected() -> None:
    """Callers must bound Ks themselves; the balance will not silently clip it."""
    with pytest.raises(ValueError, match="ks must lie within"):
        run_water_balance(40.0, _steps(), LIMITS, ks=1.4, deep_percolation_fraction=1.0)
    with pytest.raises(ValueError, match="deep_percolation_fraction must lie within"):
        run_water_balance(40.0, _steps(), LIMITS, ks=None, deep_percolation_fraction=-0.1)


def test_standardised_inputs_are_rejected() -> None:
    """A water balance is mass-conservative; z-scored depths destroy closure."""
    with pytest.raises(ValueError, match="must be declared in mm"):
        SoilLimits(
            theta_fc=0.28,
            theta_wp=0.13,
            root_depth_m=1.2,
            depletion_fraction_p=0.55,
            units="standardized",
        )


def test_inverted_soil_limits_are_rejected() -> None:
    with pytest.raises(ValueError, match="field capacity must exceed"):
        SoilLimits(
            theta_fc=0.13,
            theta_wp=0.28,
            root_depth_m=1.2,
            depletion_fraction_p=0.55,
            units="mm",
        )


def test_bounded_parameter_output_is_accepted_directly() -> None:
    """The Task 8 idiom must compose with this step without adaptation."""
    from mlet.hybrid.bounded import bounded_parameter

    raw_network_output = np.array([-8.0, 0.0, 8.0] + [0.0] * 7)
    ks = bounded_parameter(raw_network_output, FAO56_STRESS_RANGE)
    results = run_water_balance(40.0, _steps(), LIMITS, ks=ks, deep_percolation_fraction=1.0)
    assert len(results) == 10
    assert all(0.0 <= result.ks_used <= 1.0 for result in results)
