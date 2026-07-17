"""Bounded, explicitly conditional ETa scenario recurrences."""

from __future__ import annotations

from dataclasses import dataclass
import math

from mlet.outlook.state import NoIrrigationState, StateProvenance


@dataclass(frozen=True)
class ScenarioProjection:
    """One scenario-day result with every physical term needed for replay."""

    scenario: str
    eta_mm: float | None
    depletion_mm: float | None
    initial_depletion_mm: float | None
    taw_mm: float | None
    raw_mm: float | None
    ks: float | None
    potential_et_mm: float
    precip_mm: float
    assumptions: tuple[str, ...]
    state_provenance: StateProvenance | None
    unavailable_reason: str | None

    def to_record(self) -> dict[str, object]:
        """Return an artifact record that preserves conditional meaning and inputs."""
        return {
            "scenario": self.scenario,
            "availability": "available" if self.eta_mm is not None else "unavailable",
            "eta_mm": self.eta_mm,
            "potential_et_mm": self.potential_et_mm,
            "precip_mm": self.precip_mm,
            "taw_mm": self.taw_mm,
            "raw_mm": self.raw_mm,
            "initial_depletion_mm": self.initial_depletion_mm,
            "depletion_mm": self.depletion_mm,
            "ks": self.ks,
            "assumptions": list(self.assumptions),
            "state_provenance": (
                self.state_provenance.to_record()
                if self.state_provenance is not None
                else None
            ),
            "unavailable_reason": self.unavailable_reason,
        }


def project_well_watered(
    potential_et_mm: float, *, precip_mm: float
) -> ScenarioProjection:
    """Project the ample-water scenario without assuming a farmer action."""
    potential_et = _require_nonnegative(potential_et_mm, "potential_et_mm")
    precip = _require_nonnegative(precip_mm, "precip_mm")
    return ScenarioProjection(
        scenario="well_watered",
        eta_mm=potential_et,
        depletion_mm=None,
        initial_depletion_mm=None,
        taw_mm=None,
        raw_mm=None,
        ks=1.0,
        potential_et_mm=potential_et,
        precip_mm=precip,
        assumptions=("crop_water_not_limiting",),
        state_provenance=None,
        unavailable_reason=None,
    )


def project_no_irrigation(
    *,
    initial_depletion_mm: float,
    taw_mm: float,
    raw_mm: float,
    potential_et_mm: float,
    precip_mm: float,
    state_provenance: StateProvenance,
) -> ScenarioProjection:
    """Run one no-irrigation recurrence from explicitly sourced state inputs."""
    if not isinstance(state_provenance, StateProvenance):
        raise ValueError("no-irrigation scenario requires explicit StateProvenance")
    return _project_no_irrigation(
        initial_depletion_mm=initial_depletion_mm,
        taw_mm=taw_mm,
        raw_mm=raw_mm,
        potential_et_mm=potential_et_mm,
        precip_mm=precip_mm,
        state_provenance=state_provenance,
    )


def project_no_irrigation_from_state(
    state: NoIrrigationState, *, potential_et_mm: float, precip_mm: float
) -> ScenarioProjection:
    """Project or explicitly withhold the no-irrigation scenario for one state."""
    if not isinstance(state, NoIrrigationState):
        raise ValueError("no-irrigation scenario requires a NoIrrigationState")
    potential_et = _require_nonnegative(potential_et_mm, "potential_et_mm")
    precip = _require_nonnegative(precip_mm, "precip_mm")
    if not state.is_available:
        return ScenarioProjection(
            scenario="no_irrigation",
            eta_mm=None,
            depletion_mm=None,
            initial_depletion_mm=None,
            taw_mm=state.taw_mm,
            raw_mm=state.raw_mm,
            ks=None,
            potential_et_mm=potential_et,
            precip_mm=precip,
            assumptions=("no_irrigation_after_issue_time",),
            state_provenance=state.provenance,
            unavailable_reason=state.unavailable_reason,
        )
    assert state.initial_depletion_mm is not None
    return _project_no_irrigation(
        initial_depletion_mm=state.initial_depletion_mm,
        taw_mm=state.taw_mm,
        raw_mm=state.raw_mm,
        potential_et_mm=potential_et,
        precip_mm=precip,
        state_provenance=state.provenance,
    )


def _project_no_irrigation(
    *,
    initial_depletion_mm: float,
    taw_mm: float,
    raw_mm: float,
    potential_et_mm: float,
    precip_mm: float,
    state_provenance: StateProvenance,
) -> ScenarioProjection:
    taw = _require_positive(taw_mm, "taw_mm")
    raw = _require_positive(raw_mm, "raw_mm")
    initial_depletion = _require_bounded_depletion(initial_depletion_mm, taw)
    potential_et = _require_nonnegative(potential_et_mm, "potential_et_mm")
    precip = _require_nonnegative(precip_mm, "precip_mm")

    available_water_mm = max(0.0, taw - initial_depletion + precip)
    ks = min(1.0, max(0.0, available_water_mm / raw))
    eta_mm = min(potential_et, ks * potential_et)
    depletion_mm = min(taw, max(0.0, initial_depletion + eta_mm - precip))
    return ScenarioProjection(
        scenario="no_irrigation",
        eta_mm=eta_mm,
        depletion_mm=depletion_mm,
        initial_depletion_mm=initial_depletion,
        taw_mm=taw,
        raw_mm=raw,
        ks=ks,
        potential_et_mm=potential_et,
        precip_mm=precip,
        assumptions=("no_irrigation_after_issue_time",),
        state_provenance=state_provenance,
        unavailable_reason=None,
    )


def _require_bounded_depletion(value: object, taw_mm: float) -> float:
    result = _require_nonnegative(value, "initial_depletion_mm")
    if result > taw_mm:
        raise ValueError("initial_depletion_mm must be within [0, taw_mm]")
    return result


def _require_positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be positive")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _require_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite non-negative number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return result
