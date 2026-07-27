"""FAO-56 dual-coefficient daily water balance with externally supplied terms.

The physical scaffold MLET intends to make differentiable. ``Ks`` and the
deep-percolation fraction are arguments rather than internal computations, which
is the seam neuralhydrology's ``SHM`` exposes for its ``ktetha`` stress term and
``perc`` drainage split (v1.13.0, BSD-3-Clause).

Equations are transcribed from FAO-56 (Allen et al., 1998) as implemented in
vendored pyfao56 ``model.py``:

    TAW  = 1000 (theta_FC - theta_WP) Zr                        Eq. 82
    RAW  = p TAW                                                Eq. 83
    Ks   = clip((TAW - Dr) / (TAW - RAW), 0, 1)                 Eq. 84
    Ka   = Ks Kcb + Ke                                          Eq. 80
    ETa  = Ka ETref                                             Eq. 80
    DP   = max(rain + irrigation - ETa - Dr, 0)                Eq. 88
    Dr   = clip(Dr - rain - irrigation + ETa + DP, 0, TAW)     Eqs. 85, 86

With ``ks=None`` and ``deep_percolation_fraction=1.0`` this reproduces pyfao56's
trajectory to floating-point tolerance; ``tests/test_hybrid_fao56_dual.py``
asserts it against an independent transcription of the pyfao56 advance.

Nothing here trains, fits, or predicts. This module is a physical scaffold and is
not importable from the serving path.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

import numpy as np

from mlet.hybrid.bounded import (
    FAO56_DEEP_PERCOLATION_RANGE,
    FAO56_STRESS_RANGE,
    ParameterRange,
)

#: Depth units the balance accepts. A water balance is mass-conservative, so
#: standardised or otherwise rescaled depths destroy closure silently: the
#: arithmetic still runs and the result is meaningless. This mirrors
#: neuralhydrology's custom_normalization requirement on conceptual models.
REQUIRED_DEPTH_UNITS = "mm"


@dataclass(frozen=True)
class SoilLimits:
    """Static soil hydraulic limits for one field or grid cell."""

    theta_fc: float
    theta_wp: float
    root_depth_m: float
    depletion_fraction_p: float
    units: str

    def __post_init__(self) -> None:
        if self.units != REQUIRED_DEPTH_UNITS:
            raise ValueError(
                "water-balance depths must be declared in mm; a mass-conservative "
                f"balance cannot use {self.units!r} values"
            )
        values = (
            self.theta_fc,
            self.theta_wp,
            self.root_depth_m,
            self.depletion_fraction_p,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("soil limits must be finite")
        if not self.theta_fc > self.theta_wp:
            raise ValueError("field capacity must exceed the wilting point")
        if self.root_depth_m <= 0.0:
            raise ValueError("root depth must be positive")
        if not 0.0 < self.depletion_fraction_p < 1.0:
            raise ValueError("depletion fraction p must lie in (0, 1)")


@dataclass(frozen=True)
class DailyStep:
    """One day of drivers, all depths in mm."""

    eto_mm: float
    kcb: float
    ke: float
    effective_rain_mm: float
    effective_irrigation_mm: float

    def __post_init__(self) -> None:
        values = (
            self.eto_mm,
            self.kcb,
            self.ke,
            self.effective_rain_mm,
            self.effective_irrigation_mm,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("daily step drivers must be finite")
        if self.eto_mm < 0.0 or self.effective_rain_mm < 0.0 or self.effective_irrigation_mm < 0.0:
            raise ValueError("reference ET, rain, and irrigation must be non-negative")


@dataclass(frozen=True)
class DayResult:
    """Outcome of one daily advance, all depths in mm."""

    eta_mm: float
    deep_percolation_mm: float
    depletion_mm: float
    ks_used: float
    clipped: bool


def total_available_water(limits: SoilLimits) -> float:
    """Total available water in the root zone (mm). FAO-56 Eq. 82."""
    return 1000.0 * (limits.theta_fc - limits.theta_wp) * limits.root_depth_m


def readily_available_water(limits: SoilLimits) -> float:
    """Readily available water (mm). FAO-56 Eq. 83."""
    return limits.depletion_fraction_p * total_available_water(limits)


def fao56_stress_coefficient(depletion_mm: float, limits: SoilLimits) -> float:
    """Water-stress coefficient Ks. FAO-56 Eq. 84."""
    if not math.isfinite(depletion_mm):
        raise ValueError("depletion must be finite")
    taw = total_available_water(limits)
    raw = readily_available_water(limits)
    return float(np.clip((taw - depletion_mm) / (taw - raw), 0.0, 1.0))


def _validated_scalar(
    value: float,
    *,
    label: str,
    parameter_range: ParameterRange,
) -> float:
    scalar = float(value)
    if not math.isfinite(scalar):
        raise ValueError(f"{label} must be finite")
    if scalar < parameter_range.low or scalar > parameter_range.high:
        raise ValueError(
            f"{label} must lie within [{parameter_range.low}, {parameter_range.high}]; "
            "bound it with mlet.hybrid.bounded.bounded_parameter before passing it"
        )
    return scalar


def _per_step(
    value: float | Sequence[float] | np.ndarray | None,
    n_steps: int,
    label: str,
    parameter_range: ParameterRange,
) -> np.ndarray | None:
    """Broadcast a scalar or sequence to one value per step, checking bounds."""
    if value is None:
        return None
    array = np.atleast_1d(np.asarray(value, dtype=float))
    if array.size == 1:
        array = np.repeat(array, n_steps)
    if array.shape != (n_steps,):
        raise ValueError(f"{label} must be a scalar or have one value per step")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{label} must be finite")
    if np.any(array < parameter_range.low) or np.any(array > parameter_range.high):
        raise ValueError(
            f"{label} must lie within [{parameter_range.low}, {parameter_range.high}]; "
            "bound it with mlet.hybrid.bounded.bounded_parameter before passing it"
        )
    return array


def advance_one_day(
    depletion_mm: float,
    step: DailyStep,
    limits: SoilLimits,
    *,
    ks: float | None,
    deep_percolation_fraction: float,
) -> DayResult:
    """Advance the root-zone depletion by one day.

    ``ks`` of ``None`` uses FAO-56 Eq. 84. ``deep_percolation_fraction`` of 1.0
    is the FAO-56 Eq. 88 default, draining the full excess within the day.
    """
    if not math.isfinite(depletion_mm):
        raise ValueError("depletion must be finite")
    taw = total_available_water(limits)
    if depletion_mm < 0.0 or depletion_mm > taw:
        raise ValueError("depletion must lie between 0 and total available water")

    ks_used = (
        fao56_stress_coefficient(depletion_mm, limits)
        if ks is None
        else _validated_scalar(ks, label="ks", parameter_range=FAO56_STRESS_RANGE)
    )
    deep_percolation_scale = _validated_scalar(
        deep_percolation_fraction,
        label="deep_percolation_fraction",
        parameter_range=FAO56_DEEP_PERCOLATION_RANGE,
    )

    ka = ks_used * step.kcb + step.ke  # Eq. 80
    eta = ka * step.eto_mm  # Eq. 80
    inflow = step.effective_rain_mm + step.effective_irrigation_mm
    excess = max(inflow - eta - depletion_mm, 0.0)  # Eq. 88
    deep_percolation = deep_percolation_scale * excess

    unclipped = depletion_mm - inflow + eta + deep_percolation  # Eqs. 85, 86
    depletion = float(np.clip(unclipped, 0.0, taw))

    return DayResult(
        eta_mm=eta,
        deep_percolation_mm=deep_percolation,
        depletion_mm=depletion,
        ks_used=ks_used,
        clipped=bool(unclipped < 0.0 or unclipped > taw),
    )


def run_water_balance(
    initial_depletion_mm: float,
    steps: Sequence[DailyStep],
    limits: SoilLimits,
    *,
    ks: float | Sequence[float] | np.ndarray | None = None,
    deep_percolation_fraction: float | Sequence[float] | np.ndarray = 1.0,
) -> tuple[DayResult, ...]:
    """Run the daily balance over ``steps``, returning one result per day."""
    if not steps:
        raise ValueError("water balance requires at least one daily step")

    taw = total_available_water(limits)
    if not math.isfinite(initial_depletion_mm):
        raise ValueError("initial depletion must be finite")
    if initial_depletion_mm < 0.0 or initial_depletion_mm > taw:
        raise ValueError("initial depletion must lie between 0 and total available water")

    ks_series = _per_step(ks, len(steps), "ks", FAO56_STRESS_RANGE)
    dp_series = _per_step(
        deep_percolation_fraction,
        len(steps),
        "deep_percolation_fraction",
        FAO56_DEEP_PERCOLATION_RANGE,
    )
    if dp_series is None:
        raise ValueError("deep_percolation_fraction is required; FAO-56 Eq. 88 default is 1.0")

    depletion = float(initial_depletion_mm)
    results: list[DayResult] = []
    for index, step in enumerate(steps):
        result = advance_one_day(
            depletion,
            step,
            limits,
            ks=None if ks_series is None else float(ks_series[index]),
            deep_percolation_fraction=float(dp_series[index]),
        )
        results.append(result)
        depletion = result.depletion_mm
    return tuple(results)
