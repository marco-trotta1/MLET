"""Test the loss algebra and selectors without fitting the experiment."""
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ml_selective_residual import improvement, weighted_quantile, selector_features


def test_selective_risk_and_oracle_regret_identities():
    rng = np.random.default_rng(41)
    for _ in range(30):
        y, baseline, correction = rng.normal(size=(3, 100))
        mask = rng.random(100) < .7
        delta = improvement(y, baseline, correction)
        actual = np.abs(y - baseline - mask * correction)
        np.testing.assert_allclose(actual, np.abs(y - baseline) - mask * delta, atol=1e-12)
        assert np.all(np.abs(delta) <= np.abs(correction) + 1e-12)
        oracle = delta > 0
        regret = actual - np.abs(y - baseline - oracle * correction)
        np.testing.assert_allclose(regret, np.abs(delta) * (mask != oracle), atol=1e-12)


def test_own_prediction_error_does_not_rank_correction_benefit():
    y = np.array([0., 10.]); baseline = np.zeros(2); correction = np.array([.1, 9.])
    error = np.abs(y - baseline - correction)
    delta = improvement(y, baseline, correction)
    assert error[0] < error[1] and delta[0] < 0 < delta[1]


def test_weighted_threshold_preserves_station_weighting():
    values = np.array([1., 2., 3., 100.])
    weights = np.array([1/3, 1/3, 1/3, 1.])
    assert np.isclose(weighted_quantile(values, weights, .95), 100.)
    assert np.isclose(weighted_quantile(values, weights, .25), 2.)


def test_selector_features_preserve_correction_sign_and_scale():
    mean = np.array([-2., 3.]); spread = np.array([.1, .5]); distance = np.array([0., 10.])
    x = np.array([[1., 5., 2.], [4., 7., 3.]])
    features = selector_features(mean, spread, distance, x)
    np.testing.assert_allclose(features[:, 0], mean)
    np.testing.assert_allclose(features[:, 1], np.abs(mean))
    np.testing.assert_allclose(features[:, 4:], x[:, :2])


def test_matched_budget_is_exact_and_keeps_fallback_endpoints():
    from build_selective_artifacts import budget_probabilities
    rng = np.random.default_rng(14)
    for _ in range(20):
        score = rng.normal(size=81); weights = rng.uniform(.01, 2, size=81)
        for fraction in [0, .1, .5, .95, 1]:
            p = budget_probabilities(score, weights, fraction)
            assert np.all((p >= 0) & (p <= 1))
            np.testing.assert_allclose(np.average(p, weights=weights), fraction, atol=1e-12)
