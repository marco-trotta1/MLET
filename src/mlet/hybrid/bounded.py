"""Bounded dynamic parameterization of physical terms.

Adapted from neuralhydrology's ``BaseConceptualModel._get_dynamic_parameters_conceptual``
(v1.13.0, BSD-3-Clause), which maps an unbounded network output into a declared
per-parameter range with a sigmoid, per timestep.

The property that matters is not the sigmoid but the declared range: whatever a
learned function emits, including a diverging value, the physical term it
controls stays inside bounds that are constants in source with a citation. A
learned water-stress coefficient cannot become 1.4, and a learned percolation
term cannot drain a negative depth, regardless of how badly training goes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ParameterRange:
    """A physical bound on a learned term, with its units and source."""

    name: str
    low: float
    high: float
    units: str
    citation: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("parameter range needs a name")
        if not (self.low < self.high):
            raise ValueError(
                f"parameter {self.name}: low must be strictly below high, "
                f"got low={self.low} high={self.high}"
            )
        if not self.units.strip():
            raise ValueError(f"parameter {self.name} needs declared units")
        if not self.citation.strip():
            raise ValueError(
                f"parameter {self.name} needs a citation; an uncited bound is an "
                "undocumented modelling assumption"
            )


#: Water-stress coefficient Ks. FAO-56 defines Ks on [0, 1]: 1 when soil water
#: is non-limiting, 0 at full depletion of total available water.
FAO56_STRESS_RANGE = ParameterRange(
    name="ks",
    low=0.0,
    high=1.0,
    units="dimensionless",
    citation="FAO-56 Allen et al. (1998) Eq. 84",
)


#: Fraction of water above field capacity lost to deep percolation on a given
#: day. FAO-56 Eq. 88 drains the full excess within the daily step; permitting a
#: learned fraction below 1 is the departure this scaffold exists to test, so the
#: range is [0, 1] with the FAO-56 default at the upper bound.
FAO56_DEEP_PERCOLATION_RANGE = ParameterRange(
    name="deep_percolation_fraction",
    low=0.0,
    high=1.0,
    units="dimensionless",
    citation="FAO-56 Allen et al. (1998) Eq. 88",
)


def _stable_sigmoid(raw: np.ndarray) -> np.ndarray:
    """Overflow-free logistic sigmoid.

    ``1 / (1 + exp(-x))`` overflows for x below about -745. Splitting on the sign
    keeps every exponent negative.
    """
    raw = np.asarray(raw, dtype=float)
    out = np.empty_like(raw)
    positive = raw >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-raw[positive]))
    exp_raw = np.exp(raw[~positive])
    out[~positive] = exp_raw / (1.0 + exp_raw)
    return out


def bounded_parameter(raw, parameter_range: ParameterRange) -> np.ndarray:
    """Map unbounded values into ``parameter_range``, elementwise.

    Zero maps to the range midpoint; the mapping is strictly monotonic and
    saturates at the bounds.
    """
    raw = np.asarray(raw, dtype=float)
    scalar = raw.ndim == 0
    fraction = _stable_sigmoid(np.atleast_1d(raw))
    values = parameter_range.low + fraction * (parameter_range.high - parameter_range.low)
    values = np.clip(values, parameter_range.low, parameter_range.high)
    return values[0] if scalar else values


def bounded_parameters(raw, ranges: Sequence[ParameterRange]) -> dict[str, np.ndarray]:
    """Map an ``(n_steps, n_parameters)`` array to named bounded parameters."""
    raw = np.asarray(raw, dtype=float)
    ranges = tuple(ranges)
    if raw.ndim != 2:
        raise ValueError("bounded_parameters expects a 2-D (n_steps, n_parameters) array")
    if raw.shape[1] != len(ranges):
        raise ValueError("bounded_parameters needs one column per parameter range")
    result: dict[str, np.ndarray] = {}
    for index, parameter_range in enumerate(ranges):
        if parameter_range.name in result:
            raise ValueError(f"duplicate parameter range name: {parameter_range.name}")
        result[parameter_range.name] = bounded_parameter(raw[:, index], parameter_range)
    return result
