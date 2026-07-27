"""Leakage-controlled splits, metrics, and station-blocked inference."""
from __future__ import annotations

from datetime import date, datetime
from collections.abc import Sequence

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


def pinball_loss(observed: float, predicted: float, quantile: float) -> float:
    """Pinball loss for one predicted quantile level."""
    if not 0.0 < quantile < 1.0:
        raise ValueError("quantile levels must be in (0, 1)")
    error = observed - predicted
    return quantile * error if error >= 0 else (quantile - 1.0) * error


def mean_pinball_loss(
    observed: Sequence[float], quantiles: Sequence[Sequence[float]], levels: Sequence[float]
) -> float:
    """Mean pinball loss over cases and quantile levels.

    This is a proper scoring rule and a discrete approximation to the continuous
    ranked probability score. It is not CRPS: CRPS integrates the pinball loss
    over all quantile levels, and only three predicted levels are available here.
    Report it as mean pinball loss over the stated levels, never as CRPS.

    ``quantiles`` is one row per case, each row ordered to match ``levels``.
    """
    observed = list(observed)
    quantiles = [list(row) for row in quantiles]
    levels = list(levels)
    if not observed:
        raise ValueError("mean pinball loss requires at least one case")
    if len(observed) != len(quantiles):
        raise ValueError("observed and quantile rows must have the same length")
    if any(not 0.0 < level < 1.0 for level in levels):
        raise ValueError("quantile levels must be in (0, 1)")
    if any(len(row) != len(levels) for row in quantiles):
        raise ValueError("each case needs one predicted quantile per level")

    total = 0.0
    for truth, row in zip(observed, quantiles):
        for level, prediction in zip(levels, row):
            total += pinball_loss(truth, prediction, level)
    return total / (len(observed) * len(levels))


def interval_coverage(observed: Sequence[float], lower: Sequence[float], upper: Sequence[float]) -> float:
    """Fraction of cases whose observation falls inside the interval, inclusive."""
    observed = list(observed)
    lower = list(lower)
    upper = list(upper)
    if not observed:
        raise ValueError("interval coverage requires at least one case")
    if not len(observed) == len(lower) == len(upper):
        raise ValueError("observed, lower, and upper must have the same length")
    if any(low > high for low, high in zip(lower, upper)):
        raise ValueError("interval lower bound must not exceed its upper bound")
    inside = sum(1 for truth, low, high in zip(observed, lower, upper) if low <= truth <= high)
    return inside / len(observed)


def mean_interval_width(lower: Sequence[float], upper: Sequence[float]) -> float:
    """Mean interval width, the sharpness counterpart to coverage."""
    lower = list(lower)
    upper = list(upper)
    if not lower:
        raise ValueError("mean interval width requires at least one case")
    if len(lower) != len(upper):
        raise ValueError("lower and upper must have the same length")
    if any(low > high for low, high in zip(lower, upper)):
        raise ValueError("interval lower bound must not exceed its upper bound")
    return sum(high - low for low, high in zip(lower, upper)) / len(lower)
