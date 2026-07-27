"""Non-scientific deterministic checks for probabilistic scoring.

Expected values are computed from the pinball-loss definition by hand so the
test does not merely restate the implementation.
"""

import pytest

from mlet.evaluate import (
    interval_coverage,
    mean_interval_width,
    mean_pinball_loss,
    pinball_loss,
)

LEVELS = (0.1, 0.5, 0.9)


def test_pinball_loss_penalises_under_and_over_prediction_asymmetrically() -> None:
    # Under-prediction at the 0.9 level is penalised 0.9 * error.
    assert pinball_loss(observed=5.0, predicted=4.0, quantile=0.9) == pytest.approx(0.9)
    # Over-prediction at the 0.9 level is penalised only 0.1 * error.
    assert pinball_loss(observed=4.0, predicted=5.0, quantile=0.9) == pytest.approx(0.1)
    # The 0.5 level is symmetric and equals half the absolute error.
    assert pinball_loss(observed=5.0, predicted=4.0, quantile=0.5) == pytest.approx(0.5)
    assert pinball_loss(observed=4.0, predicted=5.0, quantile=0.5) == pytest.approx(0.5)


def test_pinball_loss_is_zero_on_an_exact_hit() -> None:
    for level in LEVELS:
        assert pinball_loss(observed=3.25, predicted=3.25, quantile=level) == 0.0


def test_mean_pinball_loss_averages_over_cases_and_levels() -> None:
    observed = [5.0]
    predicted = [[4.0, 4.5, 6.0]]
    expected = (
        pinball_loss(5.0, 4.0, 0.1) + pinball_loss(5.0, 4.5, 0.5) + pinball_loss(5.0, 6.0, 0.9)
    ) / 3
    assert mean_pinball_loss(observed, predicted, LEVELS) == pytest.approx(expected)


def test_mean_pinball_loss_prefers_the_sharper_correct_forecast() -> None:
    """A proper scoring rule must reward sharpness when calibration is equal."""
    observed = [5.0, 5.0, 5.0]
    sharp = [[4.8, 5.0, 5.2]] * 3
    vague = [[2.0, 5.0, 8.0]] * 3
    assert mean_pinball_loss(observed, sharp, LEVELS) < mean_pinball_loss(observed, vague, LEVELS)


def test_interval_coverage_counts_inclusive_containment() -> None:
    observed = [1.0, 2.0, 3.0, 4.0]
    lower = [0.5, 2.0, 5.0, 3.0]
    upper = [1.5, 2.5, 6.0, 4.0]
    # case 0 inside, case 1 on the lower edge, case 2 below the interval,
    # case 3 on the upper edge -> 3 of 4.
    assert interval_coverage(observed, lower, upper) == pytest.approx(0.75)


def test_mean_interval_width() -> None:
    assert mean_interval_width([1.0, 2.0], [3.0, 8.0]) == pytest.approx(4.0)


def test_inverted_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="lower bound must not exceed"):
        interval_coverage([1.0], [2.0], [1.0])
    with pytest.raises(ValueError, match="lower bound must not exceed"):
        mean_interval_width([2.0], [1.0])


def test_length_and_level_mismatches_are_rejected() -> None:
    with pytest.raises(ValueError, match="same length"):
        interval_coverage([1.0, 2.0], [0.0], [3.0])
    with pytest.raises(ValueError, match="one predicted quantile per level"):
        mean_pinball_loss([5.0], [[4.0, 5.0]], LEVELS)
    with pytest.raises(ValueError, match="quantile levels must be in \\(0, 1\\)"):
        mean_pinball_loss([5.0], [[4.0, 5.0, 6.0]], (0.0, 0.5, 0.9))


def test_empty_input_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one case"):
        mean_pinball_loss([], [], LEVELS)
    with pytest.raises(ValueError, match="at least one case"):
        interval_coverage([], [], [])
