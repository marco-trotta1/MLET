"""The stable, adapter-independent machine-readable Idaho outlook contract."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path

from mlet.outlook.contracts import OutlookDay, OutlookQuantiles
from mlet.outlook.manifest import RunManifest


_SCHEMA_VERSION = 1
_SPATIAL_RESOLUTION = "native_weather_grid"


def write_serve_contract(
    days: Sequence[OutlookDay], manifest: RunManifest, destination: Path
) -> None:
    """Write the one stable artifact a future Helios adapter may read.

    This module deliberately contains no Helios or Irrigant runtime dependency.
    It serializes named physical/conditional layers only; a delayed ETa analysis
    is never represented as a future actual-ET forecast.
    """
    if not isinstance(manifest, RunManifest):
        raise ValueError("serve contract requires a RunManifest")
    manifest.to_json()
    payload = _contract_payload(days, manifest)
    _write_new_json(Path(destination), payload)


def _contract_payload(days: Sequence[OutlookDay], manifest: RunManifest) -> dict[str, object]:
    if not days or any(not isinstance(item, OutlookDay) for item in days):
        raise ValueError("serve contract requires at least one OutlookDay record")
    sorted_days = sorted(days, key=lambda item: (item.valid_date, item.grid_id))

    issue_time = _require_utc_datetime(manifest.issued_at, "manifest issued_at")
    expected_dates = [
        issue_time.date() + timedelta(days=lead) for lead in range(1, 21)
    ]
    by_date: dict[date, list[OutlookDay]] = defaultdict(list)
    dates_by_grid: dict[str, set[date]] = defaultdict(set)
    seen: set[tuple[str, date]] = set()
    for day in sorted_days:
        if not isinstance(day.grid_id, str) or not day.grid_id.strip():
            raise ValueError("serve contract grid_id must be non-empty text")
        if not isinstance(day.valid_date, date) or isinstance(day.valid_date, datetime):
            raise ValueError("serve contract valid_date must be a date")
        key = (day.grid_id, day.valid_date)
        if key in seen:
            raise ValueError("serve contract must not duplicate a grid cell and date")
        seen.add(key)
        by_date[day.valid_date].append(day)
        dates_by_grid[day.grid_id].add(day.valid_date)
    if list(sorted(by_date)) != expected_dates:
        raise ValueError("serve contract requires exactly twenty contiguous lead dates")
    for grid_id, dates in dates_by_grid.items():
        if dates != set(expected_dates):
            raise ValueError(
                "serve contract requires every grid to contain exactly twenty "
                f"contiguous lead dates; invalid grid={grid_id!r}"
            )

    latencies = [
        (issue_time.date() - item.eta_analysis_date).days
        for item in sorted_days
        if item.eta_analysis_date is not None
    ]
    if any(latency < 1 for latency in latencies):
        raise ValueError("ETa analyses in the serve contract must predate the issue time")
    if any(item.eta_analysis_mm is None for item in sorted_days if item.eta_analysis_date is not None):
        raise ValueError("ETa analysis date and value must be present together")
    if any(item.eta_analysis_date is None for item in sorted_days if item.eta_analysis_mm is not None):
        raise ValueError("ETa analysis date and value must be present together")

    collections: list[dict[str, object]] = []
    for lead_day, valid_date in enumerate(expected_dates, start=1):
        features = [
            _feature(day, lead_day, issue_time)
            for day in sorted(by_date[valid_date], key=lambda item: item.grid_id)
        ]
        collections.append(
            {
                "valid_date": valid_date.isoformat(),
                "lead_day": lead_day,
                "type": "FeatureCollection",
                "features": features,
            }
        )

    return {
        "schema_version": _SCHEMA_VERSION,
        "run_id": manifest.run_id,
        "issued_at": _format_utc(issue_time),
        "spatial_resolution": _SPATIAL_RESOLUTION,
        "observation_latency_days": max(latencies) if latencies else None,
        "layers": _layer_definitions(),
        "feature_collections": collections,
    }


def _feature(day: OutlookDay, lead_day: int, issued_at: datetime) -> dict[str, object]:
    eta_analysis = _analysis_record(day, issued_at)
    return {
        "type": "Feature",
        "geometry": None,
        "properties": {
            "grid_id": day.grid_id,
            "valid_date": day.valid_date.isoformat(),
            "lead_day": lead_day,
            "layers": {
                "eto_mm": _quantiles(day.eto_mm, "eto_mm"),
                "potential_et_c_mm": _quantiles(
                    day.potential_et_c_mm, "potential_et_c_mm"
                ),
                "eta_well_watered_mm": _quantiles(
                    day.eta_well_watered_mm, "eta_well_watered_mm"
                ),
                "eta_no_irrigation_mm": (
                    _quantiles(day.eta_no_irrigation_mm, "eta_no_irrigation_mm")
                    if day.eta_no_irrigation_mm is not None
                    else None
                ),
                "eta_analysis_mm": eta_analysis["eta_analysis_mm"],
            },
            "eta_analysis": eta_analysis,
        },
    }


def _analysis_record(day: OutlookDay, issued_at: datetime) -> dict[str, object]:
    if day.eta_analysis_mm is None and day.eta_analysis_date is None:
        return {"eta_analysis_mm": None, "eta_analysis_date": None}
    if day.eta_analysis_mm is None or day.eta_analysis_date is None:
        raise ValueError("ETa analysis date and value must be present together")
    value = _finite_nonnegative(day.eta_analysis_mm, "eta_analysis_mm")
    if day.eta_analysis_date >= issued_at.date():
        raise ValueError("ETa analysis must be a completed day before the issue time")
    return {
        "eta_analysis_mm": value,
        "eta_analysis_date": day.eta_analysis_date.isoformat(),
    }


def _quantiles(value: OutlookQuantiles, label: str) -> dict[str, float]:
    if not isinstance(value, OutlookQuantiles):
        raise ValueError(f"{label} must contain p10, p50, and p90")
    p10 = _finite_nonnegative(value.p10, f"{label} p10")
    p50 = _finite_nonnegative(value.p50, f"{label} p50")
    p90 = _finite_nonnegative(value.p90, f"{label} p90")
    if p10 > p50 or p50 > p90:
        raise ValueError(f"{label} quantiles must be ordered")
    return {"p10": p10, "p50": p50, "p90": p90}


def _layer_definitions() -> dict[str, dict[str, object]]:
    return {
        "eto_mm": {
            "units": "mm/day",
            "kind": "forecast_ensemble_quantiles",
            "definition": "ASCE short-reference ET from weather-ensemble members.",
        },
        "potential_et_c_mm": {
            "units": "mm/day",
            "kind": "conditional_ensemble_quantiles",
            "definition": "Kc times ETo under ample-water conditions.",
        },
        "eta_analysis_mm": {
            "units": "mm/day",
            "kind": "dated_observed_analysis",
            "definition": "Latest source-available historical ETa analysis; never a future forecast.",
        },
        "eta_well_watered_mm": {
            "units": "mm/day",
            "kind": "conditional_ensemble_quantiles",
            "definition": "ETa scenario assuming crop water is not limiting.",
            "assumptions": ["crop_water_not_limiting"],
        },
        "eta_no_irrigation_mm": {
            "units": "mm/day",
            "kind": "conditional_ensemble_quantiles_or_null",
            "definition": "ETa scenario assuming no irrigation after the issue time; null when state is unavailable.",
            "assumptions": ["no_irrigation_after_issue_time"],
        },
    }


def _write_new_json(destination: Path, payload: dict[str, object]) -> None:
    if destination.exists() or destination.is_symlink():
        raise ValueError("serve contract destination must not already exist")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ValueError("serve contract destination parent must be a real directory")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.write("\n")


def _finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite non-negative number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return result


def _require_utc_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be an explicit UTC datetime")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC datetime")
    return value.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return _require_utc_datetime(value, "timestamp").isoformat().replace("+00:00", "Z")
