"""Leakage-controlled splits, metrics, and station-blocked inference."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np


def field_withheld_folds(station_ids: list[str], k: int, seed: int) -> list[tuple[list[str], list[str]]]:
    if k < 2 or k > len(station_ids):
        raise ValueError("k must be between 2 and the number of stations")
    shuffled = list(station_ids)
    np.random.default_rng(seed).shuffle(shuffled)
    buckets = [shuffled[index::k] for index in range(k)]
    return [
        (sorted(station for index, bucket in enumerate(buckets) if index != fold for station in bucket), sorted(buckets[fold]))
        for fold in range(k)
    ]


def time_split(dates: list[date], cutoff: str) -> tuple[list[int], list[int]]:
    boundary = datetime.strptime(cutoff, "%Y-%m-%d").date()
    return (
        [index for index, value in enumerate(dates) if value < boundary],
        [index for index, value in enumerate(dates) if value >= boundary],
    )


def mae(errors: list[float]) -> float:
    return float(np.mean(np.abs(errors)))


def rmse(errors: list[float]) -> float:
    return float(np.sqrt(np.mean(np.square(errors))))


def bias(predictions: list[float], truth: list[float]) -> float:
    return float(np.mean(np.asarray(predictions) - np.asarray(truth)))


def blocked_bootstrap_mae_delta(
    per_station: dict[str, tuple[list[float], list[float]]], seed: int, iters: int = 2000
) -> tuple[float, float, float]:
    if not per_station:
        raise ValueError("blocked bootstrap needs at least one station")
    stations = sorted(per_station)
    values = {
        station: (np.asarray(per_station[station][0]), np.asarray(per_station[station][1]))
        for station in stations
    }

    def pooled_delta(sample: list[str]) -> float:
        a = np.concatenate([values[station][0] for station in sample])
        b = np.concatenate([values[station][1] for station in sample])
        return float(a.mean() - b.mean())

    point = pooled_delta(stations)
    rng = np.random.default_rng(seed)
    draws = np.empty(iters, dtype=float)
    for index in range(iters):
        sample = [stations[position] for position in rng.integers(0, len(stations), size=len(stations))]
        draws[index] = pooled_delta(sample)
    lower, upper = np.percentile(draws, (2.5, 97.5))
    return point, float(lower), float(upper)
