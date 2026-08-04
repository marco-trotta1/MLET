"""Strict contract checks for the ETo-only research candidate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path

from mlet.outlook.dates import outlook_valid_dates


VALIDATION_SCOPE = {
    "formal_hindcast_layers": ["eto_mm"],
    "nonforecast_analysis_layers": ["eta_analysis_mm"],
    "unvalidated_projection_layers": [
        "potential_et_c_mm",
        "eta_well_watered_mm",
        "eta_no_irrigation_mm",
    ],
}
_CANDIDATE_FIELDS = {
    "schema_version",
    "run_id",
    "issued_at",
    "fixture_non_scientific",
    "production_status",
    "promotion_status",
    "validation_status",
    "validation_scope",
    "layers",
    "feature_collections",
}
_LAYER_FIELDS = {"units", "kind", "validation_role", "definition"}
_COLLECTION_FIELDS = {"type", "valid_date", "lead_day", "features"}
_FEATURE_FIELDS = {"type", "geometry", "properties"}
_GEOMETRY_FIELDS = {"type", "coordinates"}
_PROPERTY_FIELDS = {"grid_id", "valid_date", "lead_day", "layers"}


@dataclass(frozen=True)
class EtoCandidateContract:
    """The verified identity and coverage of one ETo candidate artifact."""

    run_id: str
    issued_at: datetime
    grid_ids: tuple[str, ...]
    valid_dates: tuple[date, ...]


def validate_eto_candidate_payload(
    payload: object,
    *,
    expected_run_id: str | None = None,
    expected_issued_at: datetime | None = None,
) -> EtoCandidateContract:
    """Validate one serialized ETo candidate and return its immutable identity."""
    _require_exact_keys(payload, _CANDIDATE_FIELDS, "ETo candidate")
    assert isinstance(payload, dict)
    if payload["schema_version"] != 1:
        raise ValueError("ETo candidate must use schema_version 1")
    run_id = _require_text(payload["run_id"], "ETo candidate run_id")
    issued_at = _parse_utc(payload["issued_at"], "ETo candidate issued_at")
    if expected_run_id is not None and run_id != expected_run_id:
        raise ValueError("ETo candidate run_id does not match the expected run")
    if expected_issued_at is not None:
        expected = _require_utc_datetime(expected_issued_at, "expected issued_at")
        if issued_at != expected:
            raise ValueError("ETo candidate issued_at does not match the expected issue time")
    if payload["fixture_non_scientific"] is not False:
        raise ValueError("ETo candidate must set fixture_non_scientific to false")
    if payload["production_status"] != "research_candidate":
        raise ValueError("ETo candidate must use production_status research_candidate")
    if payload["promotion_status"] != "not_promoted":
        raise ValueError("ETo candidate must use promotion_status not_promoted")
    if payload["validation_status"] != "evaluation_pending":
        raise ValueError("ETo candidate must use validation_status evaluation_pending")
    if payload["validation_scope"] != VALIDATION_SCOPE:
        raise ValueError("ETo candidate must retain the frozen validation scope")
    _validate_layers(payload["layers"])
    valid_dates = outlook_valid_dates(issued_at)
    grid_ids = _validate_feature_collections(payload["feature_collections"], valid_dates)
    return EtoCandidateContract(
        run_id=run_id,
        issued_at=issued_at,
        grid_ids=grid_ids,
        valid_dates=valid_dates,
    )


def load_eto_candidate(
    path: Path,
    *,
    expected_run_id: str | None = None,
    expected_issued_at: datetime | None = None,
) -> EtoCandidateContract:
    """Read and validate one duplicate-key-free ETo candidate JSON file."""
    supplied_path = Path(path)
    if supplied_path.is_symlink():
        raise ValueError("ETo candidate path must not be a symlink")
    candidate_path = supplied_path.resolve(strict=True)
    if not candidate_path.is_file():
        raise ValueError("ETo candidate path must name a regular file")
    try:
        payload = json.loads(
            candidate_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("ETo candidate must be duplicate-key-free UTF-8 JSON") from error
    return validate_eto_candidate_payload(
        payload,
        expected_run_id=expected_run_id,
        expected_issued_at=expected_issued_at,
    )


def _validate_layers(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {"eto_mm"}:
        raise ValueError("ETo candidate layers must contain only eto_mm")
    layer = value["eto_mm"]
    _require_exact_keys(layer, _LAYER_FIELDS, "ETo candidate eto_mm layer")
    assert isinstance(layer, dict)
    if layer["units"] != "mm/day":
        raise ValueError("ETo candidate eto_mm units must be mm/day")
    if layer["kind"] != "forecast_ensemble_quantiles":
        raise ValueError("ETo candidate eto_mm kind is unsupported")
    if layer["validation_role"] != "formal_hindcast_target":
        raise ValueError("ETo candidate eto_mm validation role is unsupported")
    if not isinstance(layer["definition"], str) or not layer["definition"].strip():
        raise ValueError("ETo candidate eto_mm definition must be non-empty text")


def _validate_feature_collections(
    value: object, valid_dates: tuple[date, ...]
) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) != len(valid_dates):
        raise ValueError("ETo candidate must contain exactly 20 feature collections")
    grid_ids: tuple[str, ...] | None = None
    for expected_lead, collection in enumerate(value, start=1):
        expected_date = valid_dates[expected_lead - 1]
        _require_exact_keys(collection, _COLLECTION_FIELDS, "ETo feature collection")
        assert isinstance(collection, dict)
        if collection["type"] != "FeatureCollection":
            raise ValueError("ETo feature collection type is unsupported")
        if collection["lead_day"] != expected_lead:
            raise ValueError("ETo feature collection lead days must be ordered 1 through 20")
        if collection["valid_date"] != expected_date.isoformat():
            raise ValueError("ETo feature collection valid_date does not match issue time")
        features = collection["features"]
        if not isinstance(features, list) or not features:
            raise ValueError("ETo feature collection must contain features")
        collection_grid_ids: list[str] = []
        for feature in features:
            collection_grid_ids.append(_validate_feature(feature, expected_date, expected_lead))
        if len(collection_grid_ids) != len(set(collection_grid_ids)):
            raise ValueError("ETo feature collection must not duplicate grid_id")
        ordered_grid_ids = tuple(sorted(collection_grid_ids))
        if grid_ids is None:
            grid_ids = ordered_grid_ids
        elif ordered_grid_ids != grid_ids:
            raise ValueError("ETo feature collections must cover the same grids")
    if grid_ids is None:
        raise ValueError("ETo candidate must contain at least one grid")
    return grid_ids


def _validate_feature(value: object, expected_date: date, expected_lead: int) -> str:
    _require_exact_keys(value, _FEATURE_FIELDS, "ETo feature")
    assert isinstance(value, dict)
    if value["type"] != "Feature":
        raise ValueError("ETo feature type is unsupported")
    geometry = value["geometry"]
    _require_exact_keys(geometry, _GEOMETRY_FIELDS, "ETo feature geometry")
    assert isinstance(geometry, dict)
    if geometry["type"] != "Point":
        raise ValueError("ETo feature geometry must be a Point")
    coordinates = geometry["coordinates"]
    if (
        not isinstance(coordinates, list)
        or len(coordinates) != 2
        or any(type(item) not in (int, float) or not math.isfinite(float(item)) for item in coordinates)
    ):
        raise ValueError("ETo feature coordinates must be two finite numbers")
    longitude, latitude = (float(item) for item in coordinates)
    if not -180.0 <= longitude <= 180.0 or not -90.0 <= latitude <= 90.0:
        raise ValueError("ETo feature coordinates are outside geographic bounds")
    properties = value["properties"]
    _require_exact_keys(properties, _PROPERTY_FIELDS, "ETo feature properties")
    assert isinstance(properties, dict)
    grid_id = _require_text(properties["grid_id"], "ETo feature grid_id")
    if properties["valid_date"] != expected_date.isoformat() or properties["lead_day"] != expected_lead:
        raise ValueError("ETo feature properties must match their collection")
    layers = properties["layers"]
    if not isinstance(layers, dict) or set(layers) != {"eto_mm"}:
        raise ValueError("ETo feature layers must contain only eto_mm")
    quantiles = layers["eto_mm"]
    _require_exact_keys(quantiles, {"p10", "p50", "p90"}, "ETo feature quantiles")
    assert isinstance(quantiles, dict)
    values = tuple(_finite_nonnegative(quantiles[name], f"ETo {name}") for name in ("p10", "p50", "p90"))
    if not values[0] <= values[1] <= values[2]:
        raise ValueError("ETo feature quantiles must be ordered")
    return grid_id


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{label} must be explicit UTC ISO-8601 text")
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise ValueError(f"{label} must be canonical UTC ISO-8601 text")
    return parsed.astimezone(timezone.utc)


def _require_utc_datetime(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{label} must be an explicit UTC datetime")
    return value.astimezone(timezone.utc)


def _finite_nonnegative(value: object, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)) or float(value) < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return float(value)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _require_exact_keys(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields must match the schema exactly")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
