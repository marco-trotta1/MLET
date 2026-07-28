"""Non-scientific deterministic checks for bounded dynamic parameterization."""

import numpy as np
import pytest

from mlet.hybrid.bounded import (
    FAO56_DEEP_PERCOLATION_RANGE,
    FAO56_STRESS_RANGE,
    ParameterRange,
    bounded_parameter,
    bounded_parameters,
)


RANGE = ParameterRange(
    name="ks", low=0.0, high=1.0, units="dimensionless", citation="FAO-56 Eq. 84"
)


def test_extreme_inputs_stay_inside_the_declared_range() -> None:
    """The whole point: a diverging network output cannot escape physics."""
    raw = np.array([-1e6, -50.0, 0.0, 50.0, 1e6])
    values = bounded_parameter(raw, RANGE)
    assert np.all(values >= RANGE.low)
    assert np.all(values <= RANGE.high)
    assert np.all(np.isfinite(values))


def test_zero_maps_to_the_range_midpoint() -> None:
    assert bounded_parameter(0.0, RANGE) == pytest.approx(0.5)
    wide = ParameterRange(name="dp", low=2.0, high=6.0, units="mm/day", citation="test")
    assert bounded_parameter(0.0, wide) == pytest.approx(4.0)


def test_mapping_is_monotonic() -> None:
    raw = np.linspace(-10, 10, 101)
    values = bounded_parameter(raw, RANGE)
    assert np.all(np.diff(values) > 0)


def test_large_magnitudes_do_not_overflow() -> None:
    """A naive exp(-x) sigmoid overflows near -750; this must not warn or nan."""
    with np.errstate(over="raise", invalid="raise"):
        low = bounded_parameter(np.array([-1e308]), RANGE)
        high = bounded_parameter(np.array([1e308]), RANGE)
    assert low[0] == pytest.approx(RANGE.low, abs=1e-12)
    assert high[0] == pytest.approx(RANGE.high, abs=1e-12)


def test_bounded_parameters_maps_each_column_to_its_own_range() -> None:
    raw = np.zeros((4, 2))
    result = bounded_parameters(raw, (FAO56_STRESS_RANGE, FAO56_DEEP_PERCOLATION_RANGE))
    assert set(result) == {FAO56_STRESS_RANGE.name, FAO56_DEEP_PERCOLATION_RANGE.name}
    assert result[FAO56_STRESS_RANGE.name].shape == (4,)
    assert result[FAO56_STRESS_RANGE.name][0] == pytest.approx(
        0.5 * (FAO56_STRESS_RANGE.low + FAO56_STRESS_RANGE.high)
    )


def test_column_count_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="one column per parameter range"):
        bounded_parameters(np.zeros((4, 3)), (FAO56_STRESS_RANGE,))


def test_degenerate_and_inverted_ranges_are_rejected() -> None:
    with pytest.raises(ValueError, match="low must be strictly below high"):
        ParameterRange(name="bad", low=1.0, high=1.0, units="-", citation="test")
    with pytest.raises(ValueError, match="low must be strictly below high"):
        ParameterRange(name="bad", low=2.0, high=1.0, units="-", citation="test")


def test_whitespace_only_units_or_citation_are_rejected() -> None:
    with pytest.raises(ValueError, match="needs declared units"):
        ParameterRange(name="bad", low=0.0, high=1.0, units="   ", citation="test")
    with pytest.raises(ValueError, match="needs a citation"):
        ParameterRange(name="bad", low=0.0, high=1.0, units="mm/day", citation="  ")


def test_duplicate_parameter_range_names_are_rejected() -> None:
    duplicate = ParameterRange(name="ks", low=0.0, high=1.0, units="-", citation="test")
    with pytest.raises(ValueError, match="duplicate parameter range name: ks"):
        bounded_parameters(np.zeros((3, 2)), (RANGE, duplicate))


def test_every_shipped_range_cites_its_source() -> None:
    """A bound without a citation is an undocumented modelling assumption."""
    for parameter_range in (FAO56_STRESS_RANGE, FAO56_DEEP_PERCOLATION_RANGE):
        assert parameter_range.citation
        assert parameter_range.units
