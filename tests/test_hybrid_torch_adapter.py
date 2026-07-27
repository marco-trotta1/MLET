"""Non-scientific deterministic checks for the differentiable FAO-56 balance.

Skipped when torch is absent: the hybrid extra is optional by design.
"""

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="requires the optional mlet[hybrid] extra")

from mlet.hybrid.fao56_dual import DailyStep, SoilLimits, run_water_balance
from mlet.hybrid.torch_adapter import drivers_to_tensor, torch_water_balance

LIMITS = SoilLimits(
    theta_fc=0.28, theta_wp=0.13, root_depth_m=1.2, depletion_fraction_p=0.55, units="mm"
)
RAIN = [0.0, 0.0, 18.0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0]
INITIAL = 40.0


def _steps():
    return tuple(
        DailyStep(
            eto_mm=7.0,
            kcb=1.05,
            ke=0.12,
            effective_rain_mm=r,
            effective_irrigation_mm=0.0,
        )
        for r in RAIN
    )


def test_torch_forward_matches_the_numpy_balance() -> None:
    """The contract that makes the deliberate duplication safe."""
    steps = _steps()
    ks = np.linspace(0.3, 1.0, len(steps))
    dp = np.full(len(steps), 0.8)

    expected = run_water_balance(INITIAL, steps, LIMITS, ks=ks, deep_percolation_fraction=dp)
    produced = torch_water_balance(
        INITIAL,
        drivers_to_tensor(steps),
        LIMITS,
        torch.tensor(ks, dtype=torch.float64),
        torch.tensor(dp, dtype=torch.float64),
    )

    assert produced.shape == (len(steps), 3)
    assert np.allclose(
        produced.detach().numpy()[:, 2],
        [result.depletion_mm for result in expected],
        rtol=0,
        atol=1e-6,
    )
    assert np.allclose(
        produced.detach().numpy()[:, 0],
        [result.eta_mm for result in expected],
        rtol=0,
        atol=1e-6,
    )


def test_gradients_reach_both_learned_terms() -> None:
    """Without this the scaffold is not differentiable and the design fails."""
    steps = _steps()
    ks = torch.full((len(steps),), 0.7, dtype=torch.float64, requires_grad=True)
    dp = torch.full((len(steps),), 0.8, dtype=torch.float64, requires_grad=True)

    output = torch_water_balance(INITIAL, drivers_to_tensor(steps), LIMITS, ks, dp)
    output[:, 2].sum().backward()

    assert ks.grad is not None and torch.all(torch.isfinite(ks.grad))
    assert dp.grad is not None and torch.all(torch.isfinite(dp.grad))
    # Higher Ks means more ET, so more depletion: the gradient must be positive.
    assert torch.all(ks.grad > 0)


def test_gradient_matches_a_finite_difference() -> None:
    steps = _steps()
    base_ks = 0.7
    delta = 1e-6

    ks = torch.full((len(steps),), base_ks, dtype=torch.float64, requires_grad=True)
    dp = torch.full((len(steps),), 0.8, dtype=torch.float64)
    total = torch_water_balance(INITIAL, drivers_to_tensor(steps), LIMITS, ks, dp)[:, 2].sum()
    total.backward()
    analytic = float(ks.grad.sum())

    def _total(value: float) -> float:
        series = torch.full((len(steps),), value, dtype=torch.float64)
        return float(
            torch_water_balance(INITIAL, drivers_to_tensor(steps), LIMITS, series, dp)[:, 2].sum()
        )

    numeric = (_total(base_ks + delta) - _total(base_ks - delta)) / (2 * delta)
    assert analytic == pytest.approx(numeric, rel=1e-4)


def test_depletion_stays_bounded_under_autograd() -> None:
    steps = _steps()
    taw = 1000.0 * (LIMITS.theta_fc - LIMITS.theta_wp) * LIMITS.root_depth_m
    ks = torch.full((len(steps),), 1.0, dtype=torch.float64)
    dp = torch.full((len(steps),), 1.0, dtype=torch.float64)
    depletion = torch_water_balance(INITIAL, drivers_to_tensor(steps), LIMITS, ks, dp)[:, 2]
    assert torch.all(depletion >= 0.0)
    assert torch.all(depletion <= taw + 1e-9)
