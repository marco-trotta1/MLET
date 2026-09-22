"""Bounded, explicitly conditional ETa scenario recurrences."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from mlet.outlook.state import NoIrrigationState, StateProvenance


_RECURRENCE_TOLERANCE = 1e-9


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
    issued_at: datetime
    unavailable_reason: str | None

    def __post_init__(self) -> None:
        """Reject a direct construction that cannot represent this recurrence."""
        values = _validate_projection(
            scenario=self.scenario,
            eta_mm=self.eta_mm,
            depletion_mm=self.depletion_mm,
            initial_depletion_mm=self.initial_depletion_mm,
            taw_mm=self.taw_mm,
            raw_mm=self.raw_mm,
            ks=self.ks,
            potential_et_mm=self.potential_et_mm,
            precip_mm=self.precip_mm,
            assumptions=self.assumptions,
            state_provenance=self.state_provenance,
            issued_at=self.issued_at,
            unavailable_reason=self.unavailable_reason,
        )
        for field_name, value in values.items():
            object.__setattr__(self, field_name, value)

    def assert_valid(self) -> None:
        """Recheck replay terms before an artifact can expose them."""
        _validate_projection(
            scenario=self.scenario,
            eta_mm=self.eta_mm,
            depletion_mm=self.depletion_mm,
            initial_depletion_mm=self.initial_depletion_mm,
            taw_mm=self.taw_mm,
            raw_mm=self.raw_mm,
            ks=self.ks,
            potential_et_mm=self.potential_et_mm,
            precip_mm=self.precip_mm,
            assumptions=self.assumptions,
            state_provenance=self.state_provenance,
            issued_at=self.issued_at,
            unavailable_reason=self.unavailable_reason,
        )

    def to_record(self) -> dict[str, object]:
        """Return an artifact record that preserves conditional meaning and inputs."""
        self.assert_valid()
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
                self.state_provenance.to_record(issued_at=self.issued_at)
                if self.state_provenance is not None
                else None
            ),
            "issued_at": _format_utc_timestamp(self.issued_at),
            "unavailable_reason": self.unavailable_reason,
        }


def project_well_watered(
    potential_et_mm: float, *, precip_mm: float, issued_at: datetime
) -> ScenarioProjection:
    """Project the ample-water scenario without assuming a farmer action."""
    potential_et = _require_nonnegative(potential_et_mm, "potential_et_mm")
    precip = _require_nonnegative(precip_mm, "precip_mm")
    issue_time = _require_utc_timestamp(issued_at, "issued_at")
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
        issued_at=issue_time,
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
    issued_at: datetime,
) -> ScenarioProjection:
    """Run one no-irrigation recurrence from explicitly sourced state inputs."""
    if not isinstance(state_provenance, StateProvenance):
        raise ValueError("no-irrigation scenario requires explicit StateProvenance")
    issue_time = state_provenance.assert_eligible_at(issued_at)
    return _project_no_irrigation(
        initial_depletion_mm=initial_depletion_mm,
        taw_mm=taw_mm,
        raw_mm=raw_mm,
        potential_et_mm=potential_et_mm,
        precip_mm=precip_mm,
        state_provenance=state_provenance,
        issued_at=issue_time,
    )


def project_no_irrigation_from_state(
    state: NoIrrigationState,
    *,
    potential_et_mm: float,
    precip_mm: float,
    issued_at: datetime,
) -> ScenarioProjection:
    """Project or explicitly withhold the no-irrigation scenario for one state."""
    if not isinstance(state, NoIrrigationState):
        raise ValueError("no-irrigation scenario requires a NoIrrigationState")
    state.assert_valid()
    issue_time = state.provenance.assert_eligible_at(issued_at)
    if state.issued_at != issue_time:
        raise ValueError("no-irrigation state issued_at does not match projection issued_at")
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
            issued_at=issue_time,
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
        issued_at=issue_time,
    )


def _project_no_irrigation(
    *,
    initial_depletion_mm: float,
    taw_mm: float,
    raw_mm: float,
    potential_et_mm: float,
    precip_mm: float,
    state_provenance: StateProvenance,
    issued_at: datetime,
) -> ScenarioProjection:
    taw = _require_positive(taw_mm, "taw_mm")
    raw = _require_positive(raw_mm, "raw_mm")
    initial_depletion = _require_bounded_depletion(initial_depletion_mm, taw)
    potential_et = _require_nonnegative(potential_et_mm, "potential_et_mm")
    precip = _require_nonnegative(precip_mm, "precip_mm")
    issue_time = state_provenance.assert_eligible_at(issued_at)

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
        issued_at=issue_time,
        unavailable_reason=None,
    )


def _validate_projection(
    *,
    scenario: object,
    eta_mm: object,
    depletion_mm: object,
    initial_depletion_mm: object,
    taw_mm: object,
    raw_mm: object,
    ks: object,
    potential_et_mm: object,
    precip_mm: object,
    assumptions: object,
    state_provenance: object,
    issued_at: object,
    unavailable_reason: object,
) -> dict[str, object]:
    """Validate every persisted term against its named conditional recurrence."""
    potential_et = _require_nonnegative(potential_et_mm, "potential_et_mm")
    precip = _require_nonnegative(precip_mm, "precip_mm")
    issue_time = _require_utc_timestamp(issued_at, "issued_at")

    if scenario == "well_watered":
        if assumptions != ("crop_water_not_limiting",):
            raise ValueError("well-watered scenario assumptions must be exact")
        if state_provenance is not None:
            raise ValueError("well-watered scenario must not include state_provenance")
        if unavailable_reason is not None:
            raise ValueError("well-watered scenario must not include unavailable_reason")
        if any(
            field is not None
            for field in (depletion_mm, initial_depletion_mm, taw_mm, raw_mm)
        ):
            raise ValueError("well-watered scenario must not include soil-water recurrence terms")
        eta = _require_nonnegative(eta_mm, "eta_mm")
        stress = _require_unit_interval(ks, "ks")
        if not _is_close(eta, potential_et) or not _is_close(stress, 1.0):
            raise ValueError("well-watered scenario recurrence must have eta_mm=potential_et_mm and ks=1")
        return {
            "scenario": "well_watered",
            "eta_mm": eta,
            "depletion_mm": None,
            "initial_depletion_mm": None,
            "taw_mm": None,
            "raw_mm": None,
            "ks": stress,
            "potential_et_mm": potential_et,
            "precip_mm": precip,
            "assumptions": ("crop_water_not_limiting",),
            "state_provenance": None,
            "issued_at": issue_time,
            "unavailable_reason": None,
        }

    if scenario != "no_irrigation":
        raise ValueError("scenario must be exactly well_watered or no_irrigation")
    if assumptions != ("no_irrigation_after_issue_time",):
        raise ValueError("no-irrigation scenario assumptions must be exact")
    if not isinstance(state_provenance, StateProvenance):
        raise ValueError("no-irrigation scenario requires explicit StateProvenance")
    state_provenance.assert_eligible_at(issue_time)
    taw = _require_positive(taw_mm, "taw_mm")
    raw = _require_positive(raw_mm, "raw_mm")
    if raw > taw:
        raise ValueError("raw_mm must not exceed taw_mm")

    unavailable_fields = (eta_mm, depletion_mm, initial_depletion_mm, ks)
    if all(field is None for field in unavailable_fields):
        reason = _require_text(unavailable_reason, "unavailable_reason")
        return {
            "scenario": "no_irrigation",
            "eta_mm": None,
            "depletion_mm": None,
            "initial_depletion_mm": None,
            "taw_mm": taw,
            "raw_mm": raw,
            "ks": None,
            "potential_et_mm": potential_et,
            "precip_mm": precip,
            "assumptions": ("no_irrigation_after_issue_time",),
            "state_provenance": state_provenance,
            "issued_at": issue_time,
            "unavailable_reason": reason,
        }
    if any(field is None for field in unavailable_fields):
        raise ValueError("no-irrigation scenario availability fields must be all present or all absent")
    if unavailable_reason is not None:
        raise ValueError("available no-irrigation scenario must not include unavailable_reason")

    eta = _require_nonnegative(eta_mm, "eta_mm")
    if eta > potential_et:
        raise ValueError("eta_mm must not exceed potential_et_mm")
    initial_depletion = _require_bounded_depletion(initial_depletion_mm, taw)
    depletion = _require_bounded_depletion(depletion_mm, taw, label="depletion_mm")
    stress = _require_unit_interval(ks, "ks")
    expected_ks = min(1.0, max(0.0, max(0.0, taw - initial_depletion + precip) / raw))
    expected_eta = min(potential_et, expected_ks * potential_et)
    expected_depletion = min(taw, max(0.0, initial_depletion + expected_eta - precip))
    if not (
        _is_close(stress, expected_ks)
        and _is_close(eta, expected_eta)
        and _is_close(depletion, expected_depletion)
    ):
        raise ValueError("no-irrigation scenario recurrence terms are inconsistent")
    return {
        "scenario": "no_irrigation",
        "eta_mm": eta,
        "depletion_mm": depletion,
        "initial_depletion_mm": initial_depletion,
        "taw_mm": taw,
        "raw_mm": raw,
        "ks": stress,
        "potential_et_mm": potential_et,
        "precip_mm": precip,
        "assumptions": ("no_irrigation_after_issue_time",),
        "state_provenance": state_provenance,
        "issued_at": issue_time,
        "unavailable_reason": None,
    }


def _require_bounded_depletion(value: object, taw_mm: float, *, label: str = "initial_depletion_mm") -> float:
    result = _require_nonnegative(value, label)
    if result > taw_mm:
        raise ValueError(f"{label} must be within [0, taw_mm]")
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


def _require_unit_interval(value: object, label: str) -> float:
    result = _require_nonnegative(value, label)
    if result > 1.0:
        raise ValueError(f"{label} must be within [0, 1]")
    return result


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _is_close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=_RECURRENCE_TOLERANCE)


def _require_utc_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be an explicit UTC datetime")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC datetime")
    return value.astimezone(timezone.utc)


def _format_utc_timestamp(value: datetime) -> str:
    return _require_utc_timestamp(value, "issued_at").isoformat().replace("+00:00", "Z")
