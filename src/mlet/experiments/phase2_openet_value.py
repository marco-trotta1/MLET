"""Run the frozen Phase 2 OpenET-value comparison."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from mlet import baselines, evaluate, schema
from mlet.loader import load_site_series

SEED = 20260713
K_FOLDS = 10
TIME_CUTOFF = "2019-01-01"


@dataclass(frozen=True)
class Observation:
    station_id: str
    date: date
    sample: baselines.Sample


_MODEL_TYPES = {
    "B1_CropCoefficient": baselines.CropCoefficient,
    "B2_WeatherRidge": baselines.WeatherRidge,
    "M1_OpenETDirect": baselines.OpenETDirect,
    "M2_OpenETRecal": baselines.OpenETRecal,
    "M3_OpenETRidge": baselines.OpenETRidge,
}


def _load_observations(interim_dir: str) -> dict[str, list[Observation]]:
    directory = Path(interim_dir)
    weather_path = directory / "_weather.json"
    weather: dict[str, dict[str, dict[str, float | None]]] = {}
    if weather_path.exists():
        with weather_path.open(encoding="utf-8") as handle:
            weather = json.load(handle)
    data: dict[str, list[Observation]] = {}
    for path in sorted(directory.glob("*.csv")):
        if path.name == "all_stations.csv":
            continue
        series = load_site_series(str(path))
        observations: list[Observation] = []
        for record in series.labeled():
            covariates = weather.get(series.site_id, {}).get(record.date.isoformat(), {})
            values = (covariates.get("t_avg"), covariates.get("vpd"), covariates.get("ws"))
            if (
                record.openet_et_mm is None
                or record.eto_mm is None
                or any(value is None or not math.isfinite(float(value)) for value in values)
            ):
                continue
            day_of_year = record.date.timetuple().tm_yday
            observations.append(Observation(
                station_id=series.site_id,
                date=record.date,
                sample={
                    "openet": record.openet_et_mm,
                    "eto": record.eto_mm,
                    "y": record.measured_et_mm,
                    "t_avg": float(covariates["t_avg"]),
                    "vpd": float(covariates["vpd"]),
                    "ws": float(covariates["ws"]),
                    "doy_sin": math.sin(2 * math.pi * day_of_year / 365),
                    "doy_cos": math.cos(2 * math.pi * day_of_year / 365),
                },
            ))
        if observations:
            data[series.site_id] = observations
    return data


def _empty_errors(stations: list[str]) -> dict[str, dict[str, list[float]]]:
    return {name: {station: [] for station in stations} for name in ("B0_Persistence", *_MODEL_TYPES)}


def _append_persistence(errors: dict[str, dict[str, list[float]]], observations: list[Observation]) -> None:
    previous: Observation | None = None
    for observation in sorted(observations, key=lambda item: item.date):
        if previous is not None and observation.date == previous.date + timedelta(days=1):
            errors["B0_Persistence"][observation.station_id].append(previous.sample["y"] - observation.sample["y"])
        previous = observation


def _score(
    train_data: dict[str, list[Observation]], test_data: dict[str, list[Observation]]
) -> dict[str, dict[str, list[float]]]:
    stations = sorted(set(train_data) | set(test_data))
    errors = _empty_errors(stations)
    training = [observation.sample for observations in train_data.values() for observation in observations]
    if not training:
        return errors
    for name, model_type in _MODEL_TYPES.items():
        model = model_type()
        model.fit(training)
        for station, observations in test_data.items():
            for observation in observations:
                errors[name][station].append(model.predict(observation.sample) - observation.sample["y"])
    for observations in test_data.values():
        _append_persistence(errors, observations)
    return errors


def _merge_errors(
    target: dict[str, dict[str, list[float]]], source: dict[str, dict[str, list[float]]]
) -> None:
    for name, station_errors in source.items():
        for station, values in station_errors.items():
            target[name][station].extend(values)


def _metrics(errors: dict[str, dict[str, list[float]]], stations: list[str]) -> dict[str, dict[str, float | int]]:
    output: dict[str, dict[str, float | int]] = {}
    for name, station_errors in errors.items():
        values = [error for station in stations for error in station_errors[station]]
        if not values:
            output[name] = {"mae": float("nan"), "rmse": float("nan"), "bias": float("nan"), "n": 0}
            continue
        output[name] = {
            "mae": evaluate.mae(values),
            "rmse": evaluate.rmse(values),
            "bias": evaluate.bias(values, [0.0] * len(values)),
            "n": len(values),
        }
    return output


def _h2(
    errors: dict[str, dict[str, list[float]]], stations: list[str], seed: int
) -> dict[str, object] | None:
    metrics = _metrics(errors, stations)
    candidates = [name for name in ("B1_CropCoefficient", "B2_WeatherRidge") if int(metrics[name]["n"]) > 0]
    if not candidates:
        return None
    best_free = min(candidates, key=lambda name: float(metrics[name]["mae"]))
    paired = {
        station: ([abs(value) for value in errors[best_free][station]], [abs(value) for value in errors["M3_OpenETRidge"][station]])
        for station in stations
        if errors[best_free][station] and errors["M3_OpenETRidge"][station]
    }
    if not paired:
        return None
    delta, lower, upper = evaluate.blocked_bootstrap_mae_delta(paired, seed=seed)
    baseline_mae = float(metrics[best_free]["mae"])
    reduction = delta / baseline_mae if baseline_mae else 0.0
    passes = reduction >= 0.10 and lower > 0.0
    return {
        "best_free_model": best_free,
        "mae_reduction_frac": reduction,
        "delta_mm": delta,
        "ci95": [lower, upper],
        "passes": passes,
    }


def run(interim_dir: str, landcover_path: str, seed: int = SEED) -> dict[str, object]:
    data = _load_observations(interim_dir)
    stations = sorted(data)
    if len(stations) < 2:
        raise ValueError("Phase 2 evaluation requires at least two label-ready stations")
    with open(landcover_path, encoding="utf-8") as handle:
        landcover: dict[str, str] = json.load(handle)
    field_errors = _empty_errors(stations)
    for train_ids, test_ids in evaluate.field_withheld_folds(stations, min(K_FOLDS, len(stations)), seed):
        _merge_errors(
            field_errors,
            _score(
                {station: data[station] for station in train_ids},
                {station: data[station] for station in test_ids},
            ),
        )
    field_h2 = _h2(field_errors, stations, seed)
    if field_h2 is None:
        raise ValueError("Phase 2 evaluation produced no paired H2 errors")
    passes = bool(field_h2["passes"])
    decision = (
        "OpenET adds daily-ET value (>=10% MAE reduction, CI excludes 0)"
        if passes
        else "Insufficient: OpenET does not clear the pre-registered 10% / CI>0 bar"
    )
    cutoff = date.fromisoformat(TIME_CUTOFF)
    time_train = {station: [item for item in observations if item.date < cutoff] for station, observations in data.items()}
    time_test = {station: [item for item in observations if item.date >= cutoff] for station, observations in data.items()}
    time_train = {station: values for station, values in time_train.items() if values}
    time_test = {station: values for station, values in time_test.items() if values}
    time_errors = _empty_errors(stations)
    if time_train and time_test:
        _merge_errors(time_errors, _score(time_train, time_test))
    strata: dict[str, dict[str, object] | None] = {}
    for name, selected in {
        schema.LANDCOVER_CROPLAND: [station for station in stations if landcover.get(station) == schema.LANDCOVER_CROPLAND],
        "Non-Croplands": [station for station in stations if landcover.get(station) != schema.LANDCOVER_CROPLAND],
    }.items():
        strata[name] = _h2(field_errors, selected, seed) if selected else None
    return {
        "n_stations": len(stations),
        "field_withheld": {"models": _metrics(field_errors, stations), "h2": field_h2},
        "time_withheld": {"models": _metrics(time_errors, stations), "h2": _h2(time_errors, stations, seed) if time_test else None},
        "strata": strata,
        "decision": decision,
    }


def build_phase2_result_record(
    result: dict[str, object],
    *,
    data_manifest_sha256: str,
    git_revision: str,
    seed: int = SEED,
) -> dict[str, object]:
    """Convert one fresh Phase 2 run into the manuscript result contract."""
    if not isinstance(result, dict):
        raise ValueError("Phase 2 result must be an object")
    if not _is_sha256(data_manifest_sha256):
        raise ValueError("Phase 2 data manifest must use lowercase SHA-256 hex")
    if not isinstance(git_revision, str) or not git_revision:
        raise ValueError("Phase 2 git revision must be non-empty text")
    if type(seed) is not int:
        raise ValueError("Phase 2 seed must be an integer")
    field_withheld = result.get("field_withheld")
    if not isinstance(field_withheld, dict):
        raise ValueError("Phase 2 result must contain field_withheld metrics")
    raw_models = field_withheld.get("models")
    if not isinstance(raw_models, dict) or not raw_models:
        raise ValueError("Phase 2 field_withheld models must be non-empty")
    models = []
    for name, raw_metrics in sorted(raw_models.items()):
        if not isinstance(name, str) or not isinstance(raw_metrics, dict):
            raise ValueError("Phase 2 model metrics are invalid")
        models.append(
            {
                "name": name,
                "mae_mm": _result_number(raw_metrics.get("mae"), "model MAE"),
                "rmse_mm": _result_number(raw_metrics.get("rmse"), "model RMSE"),
                "bias_mm": _result_number(raw_metrics.get("bias"), "model bias"),
                "sample_count": _result_count(raw_metrics.get("n")),
            }
        )
    raw_h2 = field_withheld.get("h2")
    if not isinstance(raw_h2, dict):
        raise ValueError("Phase 2 result must contain the field-withheld H2 result")
    ci95 = raw_h2.get("ci95")
    if not isinstance(ci95, list) or len(ci95) != 2:
        raise ValueError("Phase 2 H2 must contain a two-value confidence interval")
    return {
        "schema_version": 1,
        "kind": "mlet.phase2-openet-value-result",
        "evidence_status": "reproduced",
        "provenance": {
            "data_manifest_sha256": data_manifest_sha256,
            "git_revision": git_revision,
            "seed": seed,
        },
        "field_withheld": {"models": models},
        "h2": {
            "best_openet_free_model": _result_text(
                raw_h2.get("best_free_model"), "best OpenET-free model"
            ),
            "mae_reduction_fraction": _result_number(
                raw_h2.get("mae_reduction_frac"), "MAE reduction"
            ),
            "mae_delta_mm": _result_number(raw_h2.get("delta_mm"), "MAE delta"),
            "ci95_mm": [
                _result_number(ci95[0], "confidence interval lower bound"),
                _result_number(ci95[1], "confidence interval upper bound"),
            ],
        },
    }


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _result_number(value: object, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ValueError(f"Phase 2 {label} must be finite")
    return float(value)


def _result_count(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("Phase 2 sample count must be a positive integer")
    return value


def _result_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Phase 2 {label} must be non-empty text")
    return value
