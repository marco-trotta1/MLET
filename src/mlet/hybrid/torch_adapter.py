"""Differentiable FAO-56 dual-coefficient balance.

Requires the optional ``mlet[hybrid]`` extra. Nothing on the serving path may
import this module; ``tests/test_hybrid_isolation.py`` enforces that.

This reimplements the equations in ``fao56_dual`` using torch operations rather
than abstracting over array backends. That duplication is deliberate: a backend
shim over eleven lines of arithmetic would put indirection in the one module
that most needs to read directly against FAO-56. The duplication is held safe by
``tests/test_hybrid_torch_adapter.py::test_torch_forward_matches_the_numpy_balance``,
which asserts the two agree to 1e-6. Do not merge them.

Clamping is done with ``torch.clamp``, which passes gradient through the
unclamped region and zeroes it at the bounds. That is the intended behaviour: a
day on which the balance saturates carries no information about the learned
terms.
"""

from __future__ import annotations

from collections.abc import Sequence

import torch

from mlet.hybrid.fao56_dual import (
    DailyStep,
    SoilLimits,
    total_available_water,
)

#: Column order of the driver tensor, matching DailyStep field order.
DRIVER_COLUMNS = (
    "eto_mm",
    "kcb",
    "ke",
    "effective_rain_mm",
    "effective_irrigation_mm",
)

#: Column order of the returned tensor.
OUTPUT_COLUMNS = ("eta_mm", "deep_percolation_mm", "depletion_mm")


def drivers_to_tensor(steps: Sequence[DailyStep], dtype=torch.float64) -> torch.Tensor:
    """Stack daily drivers into an ``(n_steps, 5)`` tensor in field order."""
    if not steps:
        raise ValueError("driver tensor requires at least one daily step")
    return torch.tensor(
        [[getattr(step, name) for name in DRIVER_COLUMNS] for step in steps], dtype=dtype
    )


def torch_water_balance(
    initial_depletion_mm: float,
    drivers: torch.Tensor,
    limits: SoilLimits,
    ks: torch.Tensor,
    deep_percolation_fraction: torch.Tensor,
) -> torch.Tensor:
    """Run the differentiable daily balance.

    Returns an ``(n_steps, 3)`` tensor in ``OUTPUT_COLUMNS`` order. Gradients
    flow to ``ks`` and ``deep_percolation_fraction``.
    """
    if drivers.ndim != 2 or drivers.shape[1] != len(DRIVER_COLUMNS):
        raise ValueError(f"drivers must be (n_steps, {len(DRIVER_COLUMNS)})")
    n_steps = drivers.shape[0]
    for name, series in (("ks", ks), ("deep_percolation_fraction", deep_percolation_fraction)):
        if series.shape != (n_steps,):
            raise ValueError(f"{name} must have one value per step")

    taw = torch.tensor(total_available_water(limits), dtype=drivers.dtype, device=drivers.device)
    zero = torch.zeros((), dtype=drivers.dtype, device=drivers.device)
    depletion = torch.tensor(
        float(initial_depletion_mm), dtype=drivers.dtype, device=drivers.device
    )

    rows = []
    for index in range(n_steps):
        eto, kcb, ke, rain, irrigation = drivers[index]

        ka = ks[index] * kcb + ke  # Eq. 80
        eta = ka * eto  # Eq. 80
        inflow = rain + irrigation
        excess = torch.clamp(inflow - eta - depletion, min=zero)  # Eq. 88
        deep_percolation = deep_percolation_fraction[index] * excess

        depletion = torch.clamp(
            depletion - inflow + eta + deep_percolation, min=zero, max=taw
        )  # Eqs. 85, 86
        rows.append(torch.stack((eta, deep_percolation, depletion)))

    return torch.stack(rows)
