"""Normalize delayed OpenET analyses without turning them into forecasts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
import math


@dataclass(frozen=True)
class EtaAnalysis:
    """One observed-date OpenET ETa analysis for a native weather grid cell."""

    grid_id: str
    eta_analysis_mm: float
    observed_through: date
    retrieved_at: datetime
    latency_days: int
    model: str
    model_version: str


def normalize_openet_state(
    rows: Iterable[dict[str, object]], retrieved_at: str
) -> list[EtaAnalysis]:
    """Return dated analyses, rejecting future observations and duplicate rows.

    An empty source remains empty: this boundary never fills a missing state
    from a later OpenET observation.
    """
    retrieval_time = _parse_utc_timestamp(retrieved_at)
    result: list[EtaAnalysis] = []
    seen_keys: set[tuple[str, str, str, date]] = set()
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"OpenET row {row_index} must be an object")
        grid_id = _require_text(row, "grid_id", row_index)
        model = _require_text(row, "model", row_index)
        model_version = _require_text(row, "model_version", row_index)
        observed_through = _require_date(row, "observation_date", row_index)
        if observed_through > retrieval_time.date():
            raise ValueError("OpenET observation date is later than retrieval/run time")
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
                retrieved_at=retrieval_time,
                latency_days=(retrieval_time.date() - observed_through).days,
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


def _parse_utc_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("retrieved_at must be an explicit UTC ISO-8601 timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError("retrieved_at must be an explicit UTC ISO-8601 timestamp ending in Z") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("retrieved_at must be an explicit UTC ISO-8601 timestamp ending in Z")
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
