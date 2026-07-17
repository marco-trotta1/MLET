"""Explicitly sourced soil-water state and dated OpenET ETa analyses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import math

from mlet.sources.openet_state import EtaAnalysis


@dataclass(frozen=True)
class StateProvenance:
    """Traceable source identity for a recorded initial soil-water state."""

    source_name: str
    source_version: str
    source_uri: str
    observed_date: date

    def __post_init__(self) -> None:
        _require_text(self.source_name, "state provenance source_name")
        _require_text(self.source_version, "state provenance source_version")
        if not isinstance(self.source_uri, str) or not self.source_uri.startswith("https://"):
            raise ValueError("state provenance source_uri must be an HTTPS URL")
        if not isinstance(self.observed_date, date):
            raise ValueError("state provenance observed_date must be a date")

    def to_record(self) -> dict[str, str]:
        """Return the state source fields that a run receipt must retain."""
        return {
            "source_name": self.source_name,
            "source_version": self.source_version,
            "source_uri": self.source_uri,
            "observed_date": self.observed_date.isoformat(),
        }


@dataclass(frozen=True)
class NoIrrigationState:
    """A recorded initial depletion or an explicit reason it is unavailable."""

    grid_id: str
    taw_mm: float
    raw_mm: float
    initial_depletion_mm: float | None
    provenance: StateProvenance
    unavailable_reason: str | None

    @property
    def is_available(self) -> bool:
        """Whether a bounded depletion was supplied by the recorded state source."""
        return self.initial_depletion_mm is not None and self.unavailable_reason is None

    def to_record(self) -> dict[str, object]:
        """Expose all state terms used or withheld by the no-irrigation branch."""
        return {
            "grid_id": self.grid_id,
            "taw_mm": self.taw_mm,
            "raw_mm": self.raw_mm,
            "initial_depletion_mm": self.initial_depletion_mm,
            "availability": "available" if self.is_available else "unavailable",
            "unavailable_reason": self.unavailable_reason,
            "state_provenance": self.provenance.to_record(),
        }


@dataclass(frozen=True)
class EtaAnalysisLayer:
    """A dated ETa analysis, or a transparent absence when no state is eligible."""

    eta_analysis_mm: float | None
    eta_analysis_date: date | None
    source_available_at: datetime | None
    source_model: str | None
    source_model_version: str | None

    def to_record(self) -> dict[str, object]:
        """Serialize an observed analysis without recasting it as a forecast."""
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
        }


def initialize_no_irrigation_state(
    *,
    grid_id: str,
    taw_mm: float,
    raw_mm: float,
    initial_depletion_mm: float | None,
    provenance: StateProvenance,
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
        unavailable_reason=unavailable_reason,
    )


def eta_analysis_from_openet(analysis: EtaAnalysis | None) -> EtaAnalysisLayer:
    """Represent a dated OpenET observation exactly, or retain a missing value."""
    if analysis is None:
        return EtaAnalysisLayer(
            eta_analysis_mm=None,
            eta_analysis_date=None,
            source_available_at=None,
            source_model=None,
            source_model_version=None,
        )
    if not isinstance(analysis, EtaAnalysis):
        raise ValueError("eta analysis must be an EtaAnalysis record or None")
    return EtaAnalysisLayer(
        eta_analysis_mm=analysis.eta_analysis_mm,
        eta_analysis_date=analysis.observed_through,
        source_available_at=analysis.source_available_at,
        source_model=analysis.model,
        source_model_version=analysis.model_version,
    )


def _bounded_depletion_or_none(value: object, taw_mm: float) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= taw_mm:
        return None
    return result


def _require_positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite positive number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be a finite positive number")
    return result


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _format_utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("OpenET source_available_at must be UTC")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
