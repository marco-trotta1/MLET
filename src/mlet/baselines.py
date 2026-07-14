"""Transparent, fixed Phase 2 ET comparison models implemented with numpy."""
from __future__ import annotations

from typing import TypeAlias

import numpy as np

Sample: TypeAlias = dict[str, float]
RIDGE_LAMBDA = 1.0
_WEATHER_FEATURES = ("eto", "doy_sin", "doy_cos", "t_avg", "vpd", "ws")


class Persistence:
    """B0: today's prediction is yesterday's observed ET (oracle-ish floor)."""

    def predict_series(self, targets: list[float]) -> list[float | None]:
        return [None, *targets[:-1]] if targets else []


class CropCoefficient:
    """B1: static train-fitted ratio of corrected ET to reference ET."""

    def __init__(self) -> None:
        self.k = 0.0

    def fit(self, train: list[Sample]) -> None:
        ratios = [row["y"] / row["eto"] for row in train if row["eto"] > 0]
        self.k = float(np.mean(ratios)) if ratios else 0.0

    def predict(self, sample: Sample) -> float:
        return self.k * sample["eto"]


class OpenETDirect:
    """M1: OpenET ensemble without calibration."""

    def fit(self, train: list[Sample]) -> None:
        del train

    def predict(self, sample: Sample) -> float:
        return sample["openet"]


class OpenETRecal:
    """M2: train-fitted ordinary-least-squares calibration of OpenET."""

    def __init__(self) -> None:
        self.intercept = 0.0
        self.slope = 1.0

    def fit(self, train: list[Sample]) -> None:
        x = np.array([row["openet"] for row in train], dtype=float)
        y = np.array([row["y"] for row in train], dtype=float)
        if not len(x):
            raise ValueError("OpenETRecal requires at least one training row")
        design = np.column_stack((np.ones_like(x), x))
        coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
        self.intercept, self.slope = (float(coefficients[0]), float(coefficients[1]))

    def predict(self, sample: Sample) -> float:
        return self.intercept + self.slope * sample["openet"]


class _Ridge:
    """Train-standardized fixed-penalty ridge regression."""

    def __init__(self, features: tuple[str, ...], penalty: float = RIDGE_LAMBDA) -> None:
        self._features = features
        self._penalty = penalty
        self._mean: np.ndarray | None = None
        self._std: np.ndarray | None = None
        self._coefficients: np.ndarray | None = None
        self._intercept = 0.0

    def fit(self, train: list[Sample]) -> None:
        if not train:
            raise ValueError("ridge model requires at least one training row")
        matrix = np.array([[row[name] for name in self._features] for row in train], dtype=float)
        target = np.array([row["y"] for row in train], dtype=float)
        self._mean = matrix.mean(axis=0)
        raw_std = matrix.std(axis=0)
        self._std = np.where(raw_std == 0, 1.0, raw_std)
        standardized = (matrix - self._mean) / self._std
        gram = standardized.T @ standardized + self._penalty * np.eye(standardized.shape[1])
        self._coefficients = np.linalg.solve(gram, standardized.T @ (target - target.mean()))
        self._intercept = float(target.mean())

    def predict(self, sample: Sample) -> float:
        if self._mean is None or self._std is None or self._coefficients is None:
            raise RuntimeError("model must be fit before predict")
        values = np.array([sample[name] for name in self._features], dtype=float)
        return float(self._intercept + ((values - self._mean) / self._std) @ self._coefficients)


class WeatherRidge:
    """B2: reference ET, seasonality, and meteorological covariates only."""

    def __init__(self) -> None:
        self._ridge = _Ridge(_WEATHER_FEATURES)

    def fit(self, train: list[Sample]) -> None:
        self._ridge.fit(train)

    def predict(self, sample: Sample) -> float:
        return self._ridge.predict(sample)


class OpenETRidge:
    """M3: B2's predictors plus OpenET ensemble ET."""

    def __init__(self) -> None:
        self._ridge = _Ridge(("openet", *_WEATHER_FEATURES))

    def fit(self, train: list[Sample]) -> None:
        self._ridge.fit(train)

    def predict(self, sample: Sample) -> float:
        return self._ridge.predict(sample)
