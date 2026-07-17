"""Explicitly sourced soil-water state and dated OpenET ETa analyses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import math
from urllib.parse import urlparse

from mlet.sources.openet_state import EtaAnalysis
from mlet.outlook.dates import idaho_local_date


@dataclass(frozen=True)
class StateProvenance:
    """Traceable source identity for a recorded initial soil-water state."""

    source_name: str
    source_version: str
    source_uri: str
    observed_date: date
    source_available_at: datetime

    def __post_init__(self) -> None:
        _, _, _, _, source_available_at = validate_state_provenance(self)
        object.__setattr__(
            self,
            "source_available_at",
            source_available_at,
        )

    def to_record(self, *, issued_at: datetime) -> dict[str, str]:
        """Return the state source fields that a run receipt must retain."""
        self.assert_eligible_at(issued_at)
        return {
            "source_name": self.source_name,
            "source_version": self.source_version,
            "source_uri": self.source_uri,
            "observed_date": self.observed_date.isoformat(),
            "source_available_at": _format_utc_timestamp(self.source_available_at),
        }

    def assert_eligible_at(self, issued_at: datetime) -> datetime:
        """Return a canonical issue time only when this state was then knowable."""
        return _validate_provenance_at_issue(self, issued_at)


@dataclass(frozen=True)
class NoIrrigationState:
    """A recorded initial depletion or an explicit reason it is unavailable."""

    grid_id: str
    taw_mm: float
    raw_mm: float
    initial_depletion_mm: float | None
    provenance: StateProvenance
    issued_at: datetime
    unavailable_reason: str | None

    def __post_init__(self) -> None:
        taw, raw, depletion, issue_time, unavailable_reason = _validate_no_irrigation_state(
            grid_id=self.grid_id,
            taw_mm=self.taw_mm,
            raw_mm=self.raw_mm,
            initial_depletion_mm=self.initial_depletion_mm,
            provenance=self.provenance,
            issued_at=self.issued_at,
            unavailable_reason=self.unavailable_reason,
        )
        object.__setattr__(self, "taw_mm", taw)
        object.__setattr__(self, "raw_mm", raw)
        object.__setattr__(self, "initial_depletion_mm", depletion)
        object.__setattr__(self, "issued_at", issue_time)
        object.__setattr__(self, "unavailable_reason", unavailable_reason)

    def assert_valid(self) -> None:
        """Verify this state cannot be relabeled as an available invalid state."""
        _validate_no_irrigation_state(
            grid_id=self.grid_id,
            taw_mm=self.taw_mm,
            raw_mm=self.raw_mm,
            initial_depletion_mm=self.initial_depletion_mm,
            provenance=self.provenance,
            issued_at=self.issued_at,
            unavailable_reason=self.unavailable_reason,
        )

    @property
    def is_available(self) -> bool:
        """Whether a bounded depletion was supplied by the recorded state source."""
        return self.initial_depletion_mm is not None and self.unavailable_reason is None

    def to_record(self) -> dict[str, object]:
        """Expose all state terms used or withheld by the no-irrigation branch."""
        self.assert_valid()
        return {
            "grid_id": self.grid_id,
            "taw_mm": self.taw_mm,
            "raw_mm": self.raw_mm,
            "initial_depletion_mm": self.initial_depletion_mm,
            "availability": "available" if self.is_available else "unavailable",
            "unavailable_reason": self.unavailable_reason,
            "issued_at": _format_utc_timestamp(self.issued_at),
            "state_provenance": self.provenance.to_record(issued_at=self.issued_at),
        }


@dataclass(frozen=True)
class EtaAnalysisLayer:
    """A dated ETa analysis, or a transparent absence when no state is eligible."""

    eta_analysis_mm: float | None
    eta_analysis_date: date | None
    source_available_at: datetime | None
    source_model: str | None
    source_model_version: str | None
    issued_at: datetime

    def __post_init__(self) -> None:
        issue_time, source_available_at = _validate_eta_analysis_layer(
            eta_analysis_mm=self.eta_analysis_mm,
            eta_analysis_date=self.eta_analysis_date,
            source_available_at=self.source_available_at,
            source_model=self.source_model,
            source_model_version=self.source_model_version,
            issued_at=self.issued_at,
        )
        object.__setattr__(self, "issued_at", issue_time)
        object.__setattr__(self, "source_available_at", source_available_at)

    def assert_eligible(self) -> None:
        """Ensure a direct construction cannot serialize a future analysis."""
        _validate_eta_analysis_layer(
            eta_analysis_mm=self.eta_analysis_mm,
            eta_analysis_date=self.eta_analysis_date,
            source_available_at=self.source_available_at,
            source_model=self.source_model,
            source_model_version=self.source_model_version,
            issued_at=self.issued_at,
        )

    def to_record(self) -> dict[str, object]:
        """Serialize an observed analysis without recasting it as a forecast."""
        self.assert_eligible()
        return {
            "eta_analysis_mm": self.eta_analysis_mm,
            "eta_analysis_date": (
                self.eta_analysis_date.isoformat()
                if self.eta_analysis_date is not None
                else None
            ),
            "source_available_at": (
                _format_utc_timestamp(self.source_available_at)
                if self.source_available_at is not None
                else None
            ),
            "source_model": self.source_model,
            "source_model_version": self.source_model_version,
            "issued_at": _format_utc_timestamp(self.issued_at),
        }


def initialize_no_irrigation_state(
    *,
    grid_id: str,
    taw_mm: float,
    raw_mm: float,
    initial_depletion_mm: float | None,
    provenance: StateProvenance,
    issued_at: datetime,
) -> NoIrrigationState:
    """Accept only a bounded recorded depletion; otherwise make the branch unavailable.

    This function intentionally does not accept an ETa observation.  ETa cannot
    determine root-zone depletion without a separately declared state model and
    conversion, so no such conversion is inferred here.
    """
    _require_text(grid_id, "grid_id")
    taw = _require_positive(taw_mm, "taw_mm")
    raw = _require_positive(raw_mm, "raw_mm")
    if not isinstance(provenance, StateProvenance):
        raise ValueError("no-irrigation state requires explicit StateProvenance")
    issue_time = _require_utc_timestamp(issued_at, "issued_at")
    _validate_provenance_at_issue(provenance, issue_time)
    depletion = _bounded_depletion_or_none(initial_depletion_mm, taw)
    unavailable_reason = (
        None
        if depletion is not None
        else "recorded initial_depletion_mm is absent or outside [0, taw_mm]"
    )
    return NoIrrigationState(
        grid_id=grid_id,
        taw_mm=taw,
        raw_mm=raw,
        initial_depletion_mm=depletion,
        provenance=provenance,
        issued_at=issue_time,
        unavailable_reason=unavailable_reason,
    )


def eta_analysis_from_openet(
    analysis: EtaAnalysis | None, *, issued_at: datetime
) -> EtaAnalysisLayer:
    """Represent a dated OpenET observation exactly, or retain a missing value."""
    issue_time = _require_utc_timestamp(issued_at, "issued_at")
    if analysis is None:
        return EtaAnalysisLayer(
            eta_analysis_mm=None,
            eta_analysis_date=None,
            source_available_at=None,
            source_model=None,
            source_model_version=None,
            issued_at=issue_time,
        )
    if not isinstance(analysis, EtaAnalysis):
        raise ValueError("eta analysis must be an EtaAnalysis record or None")
    source_available_at = _require_utc_timestamp(
        analysis.source_available_at, "OpenET source_available_at"
    )
    observed_through = _require_date(analysis.observed_through, "OpenET observed_through")
    if source_available_at > issue_time:
        raise ValueError("OpenET source_available_at is later than issued_at")
    if observed_through >= idaho_local_date(issue_time):
        raise ValueError("OpenET observed_through must be strictly before issued_at")
    return EtaAnalysisLayer(
        eta_analysis_mm=analysis.eta_analysis_mm,
        eta_analysis_date=observed_through,
        source_available_at=source_available_at,
        source_model=analysis.model,
        source_model_version=analysis.model_version,
        issued_at=issue_time,
    )


def _bounded_depletion_or_none(value: object, taw_mm: float) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= taw_mm:
        return None
    return result


def _validate_no_irrigation_state(
    *,
    grid_id: object,
    taw_mm: object,
    raw_mm: object,
    initial_depletion_mm: object,
    provenance: object,
    issued_at: object,
    unavailable_reason: object,
) -> tuple[float, float, float | None, datetime, str | None]:
    _require_text(grid_id, "grid_id")
    taw = _require_positive(taw_mm, "taw_mm")
    raw = _require_positive(raw_mm, "raw_mm")
    if raw > taw:
        raise ValueError("raw_mm must not exceed taw_mm")
    if not isinstance(provenance, StateProvenance):
        raise ValueError("no-irrigation state requires explicit StateProvenance")
    issue_time = _validate_provenance_at_issue(provenance, issued_at)
    if initial_depletion_mm is None:
        reason = _require_text(unavailable_reason, "unavailable_reason")
        return taw, raw, None, issue_time, reason
    depletion = _require_bounded_depletion(initial_depletion_mm, taw)
    if unavailable_reason is not None:
        raise ValueError(
            "available no-irrigation state must not include unavailable_reason"
        )
    return taw, raw, depletion, issue_time, None


def _validate_eta_analysis_layer(
    *,
    eta_analysis_mm: object,
    eta_analysis_date: object,
    source_available_at: object,
    source_model: object,
    source_model_version: object,
    issued_at: object,
) -> tuple[datetime, datetime | None]:
    issue_time = _require_utc_timestamp(issued_at, "issued_at")
    fields = (
        eta_analysis_mm,
        eta_analysis_date,
        source_available_at,
        source_model,
        source_model_version,
    )
    if all(field is None for field in fields):
        return issue_time, None
    if any(field is None for field in fields):
        raise ValueError("ETa analysis fields must be all present or all absent")
    _require_nonnegative(eta_analysis_mm, "eta_analysis_mm")
    analysis_date = _require_date(eta_analysis_date, "eta_analysis_date")
    availability = _require_utc_timestamp(source_available_at, "source_available_at")
    _require_text(source_model, "source_model")
    _require_text(source_model_version, "source_model_version")
    if availability > issue_time:
        raise ValueError("ETa source_available_at is later than issued_at")
    if analysis_date >= idaho_local_date(issue_time):
        raise ValueError("ETa analysis date must be strictly before issued_at")
    return issue_time, availability


def _require_positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite positive number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be a finite positive number")
    return result


def _require_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite non-negative number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return result


def _require_bounded_depletion(value: object, taw_mm: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("initial_depletion_mm must be within [0, taw_mm]")
    depletion = float(value)
    if not math.isfinite(depletion) or not 0.0 <= depletion <= taw_mm:
        raise ValueError("initial_depletion_mm must be within [0, taw_mm]")
    return depletion


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _require_date(value: object, label: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{label} must be a date")
    return value


def _require_utc_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be an explicit UTC datetime")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC datetime")
    return value.astimezone(timezone.utc)


def _validate_provenance_at_issue(
    provenance: StateProvenance, issued_at: datetime
) -> datetime:
    _, _, _, observed_date, source_available_at = validate_state_provenance(provenance)
    issue_time = _require_utc_timestamp(issued_at, "issued_at")
    if source_available_at > issue_time:
        raise ValueError("state provenance source_available_at is later than issued_at")
    if observed_date >= idaho_local_date(issue_time):
        raise ValueError(
            "state provenance observed_date must be a completed day strictly before issued_at"
        )
    return issue_time


def validate_state_provenance(
    provenance: object,
) -> tuple[str, str, str, date, datetime]:
    """Validate a state receipt before it is used or serialized.

    Frozen dataclasses can still be deliberately mutated through low-level
    Python APIs, so eligibility checks call this complete structural validator
    rather than trusting construction-time checks alone.
    """
    if not isinstance(provenance, StateProvenance):
        raise ValueError("no-irrigation state requires explicit StateProvenance")
    source_name = _require_text(
        provenance.source_name, "state provenance source_name"
    )
    source_version = _require_text(
        provenance.source_version, "state provenance source_version"
    )
    source_uri = _require_https_url(
        provenance.source_uri, "state provenance source_uri"
    )
    observed_date = _require_date(
        provenance.observed_date, "state provenance observed_date"
    )
    source_available_at = _require_utc_timestamp(
        provenance.source_available_at, "state provenance source_available_at"
    )
    return source_name, source_version, source_uri, observed_date, source_available_at


def _require_https_url(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an HTTPS URL")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{label} must be an HTTPS URL")
    return value


def _format_utc_timestamp(value: datetime) -> str:
    return _require_utc_timestamp(value, "timestamp").isoformat().replace("+00:00", "Z")
