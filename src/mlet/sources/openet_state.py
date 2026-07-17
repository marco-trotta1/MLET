"""Normalize availability-gated OpenET analyses without turning them into forecasts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
import math

from mlet.outlook.dates import idaho_local_date


@dataclass(frozen=True)
class EtaAnalysis:
    """One completed-day OpenET ETa analysis eligible at a recorded issue time."""

    grid_id: str
    eta_analysis_mm: float
    observed_through: date
    issued_at: datetime
    source_available_at: datetime
    retrieved_at: datetime
    latency_days: int
    model: str
    model_version: str


def normalize_openet_state(
    rows: Iterable[dict[str, object]], *, issued_at: str, retrieved_at: str
) -> list[EtaAnalysis]:
    """Return only source-available completed-day analyses for ``issued_at``.

    ``retrieved_at`` records when an archived artifact was obtained; it is not
    an eligibility substitute.  Each immutable row must instead declare the
    strict-UTC time at which that exact model/version observation was available.
    """
    issue_time = _parse_utc_timestamp(issued_at, "issued_at")
    retrieval_time = _parse_utc_timestamp(retrieved_at, "retrieved_at")
    result: list[EtaAnalysis] = []
    seen_keys: set[tuple[str, str, str, date]] = set()
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"OpenET row {row_index} must be an object")
        grid_id = _require_text(row, "grid_id", row_index)
        model = _require_text(row, "model", row_index)
        model_version = _require_text(row, "model_version", row_index)
        observed_through = _require_date(row, "observation_date", row_index)
        if observed_through >= idaho_local_date(issue_time):
            raise ValueError(
                "OpenET observation_date must be a completed day strictly before issued_at"
            )
        source_available_at = _parse_utc_timestamp(
            row.get("source_available_at"),
            f"OpenET row {row_index} field source_available_at",
        )
        if source_available_at > issue_time:
            raise ValueError(
                "OpenET row source_available_at is later than the historical issued_at cutoff"
            )
        eta_analysis_mm = _require_nonnegative_number(row, "eta_analysis_mm", row_index)
        key = (grid_id, model, model_version, observed_through)
        if key in seen_keys:
            raise ValueError("OpenET contains a duplicate grid/model/observation row")
        seen_keys.add(key)
        result.append(
            EtaAnalysis(
                grid_id=grid_id,
                eta_analysis_mm=eta_analysis_mm,
                observed_through=observed_through,
                issued_at=issue_time,
                source_available_at=source_available_at,
                retrieved_at=retrieval_time,
                latency_days=(idaho_local_date(issue_time) - observed_through).days,
                model=model,
                model_version=model_version,
            )
        )
    return sorted(
        result,
        key=lambda item: (
            item.grid_id,
            item.observed_through,
            item.model,
            item.model_version,
        ),
    )


def _parse_utc_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(
            f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be an explicit UTC ISO-8601 timestamp ending in Z")
    return parsed.astimezone(timezone.utc)


def _require_text(row: Mapping[str, object], name: str, row_index: int) -> str:
    value = row.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"OpenET row {row_index} field {name} must be non-empty text")
    return value.strip()


def _require_date(row: Mapping[str, object], name: str, row_index: int) -> date:
    value = row.get(name)
    if not isinstance(value, str):
        raise ValueError(f"OpenET row {row_index} field {name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"OpenET row {row_index} field {name} must be YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise ValueError(f"OpenET row {row_index} field {name} must be YYYY-MM-DD")
    return parsed


def _require_nonnegative_number(
    row: Mapping[str, object], name: str, row_index: int
) -> float:
    value = row.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"OpenET row {row_index} field {name} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(
            f"OpenET row {row_index} field {name} must be finite and non-negative"
        )
    return result
