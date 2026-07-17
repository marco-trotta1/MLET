"""Non-serving, leakage-safe residual-model primitives for the ET outlook.

The physical ETo/ETc outlook remains the product baseline.  These functions
only support a separately evaluated research experiment; they never modify an
outlook artifact or make a release decision.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
import math

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

from mlet.outlook.dates import outlook_valid_date


FEATURES = (
    "lead_day",
    "eto_p50",
    "eto_spread",
    "precip_p50",
    "crop_fraction",
    "kc",
    "taw_mm",
    "initial_depletion_mm",
    "eta_analysis_age_days",
)
QUANTILES = (0.1, 0.5, 0.9)
MODEL_RANDOM_SEED = 20260717
MODEL_HYPERPARAMETERS = {
    "loss": "quantile",
    "n_estimators": 80,
    "max_depth": 2,
    "min_samples_leaf": 2,
    "learning_rate": 0.05,
}


def calendar_season(day: date) -> str:
    """Return the fixed meteorological season for an immutable valid date."""
    if day.month in (12, 1, 2):
        return "DJF"
    if day.month in (3, 4, 5):
        return "MAM"
    if day.month in (6, 7, 8):
        return "JJA"
    return "SON"


@dataclass(frozen=True)
class OutlookQuantiles:
    """An ordered predictive interval in millimetres per day."""

    p10: float
    p50: float
    p90: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.p10, self.p50, self.p90)):
            raise ValueError("outlook quantiles must be finite")
        if self.p10 > self.p50 or self.p50 > self.p90:
            raise ValueError("outlook quantiles must be ordered")


@dataclass(frozen=True)
class ResidualCase:
    """One archived case, including only issue-time available features.

    ``physical_p50`` is the unchanged physics baseline and ``target_mm`` is a
    later-observed evaluation target.  A model learns ``target - physical``.
    """

    case_id: str
    role: str
    layer: str
    target_kind: str
    issue_time: datetime
    valid_date: str
    spatial_block: str
    season: str
    feature_available_at: tuple[tuple[str, datetime], ...]
    features: tuple[float, ...]
    physical_p50: float
    target_mm: float

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("residual case_id must be non-empty text")
        if self.role not in {"train", "calibration", "test"}:
            raise ValueError("residual role must be train, calibration, or test")
        if self.layer != "eta_well_watered_mm":
            raise ValueError("residual experiment is restricted to eta_well_watered_mm")
        if self.target_kind != "declared_well_watered_scenario_target":
            raise ValueError("residual target must retain the declared well-watered scenario kind")
        issue = _strict_utc(self.issue_time, "issue_time")
        object.__setattr__(self, "issue_time", issue)
        if not isinstance(self.valid_date, str):
            raise ValueError("residual valid_date must be ISO calendar-date text")
        try:
            valid_day = date.fromisoformat(self.valid_date)
        except ValueError as error:
            raise ValueError("residual valid_date must be ISO calendar-date text") from error
        if not isinstance(self.spatial_block, str) or not self.spatial_block:
            raise ValueError("residual spatial_block must be non-empty text")
        names = tuple(name for name, _available_at in self.feature_available_at)
        if names != FEATURES:
            raise ValueError("residual feature availability must name FEATURES in order")
        for name, available_at in self.feature_available_at:
            if _strict_utc(available_at, f"feature {name} available_at") > issue:
                raise ValueError(f"feature {name} was available after issue_time")
        if len(self.features) != len(FEATURES) or not all(math.isfinite(value) for value in self.features):
            raise ValueError("residual features must be finite and match FEATURES")
        lead = self.features[0]
        if not lead.is_integer() or not 1 <= int(lead) <= 20:
            raise ValueError("residual lead_day must be an integer from 1 through 20")
        if valid_day != outlook_valid_date(issue, int(lead)):
            raise ValueError(
                "residual valid_date must equal the Idaho-local outlook date for lead_day"
            )
        derived_season = calendar_season(valid_day)
        if self.season != derived_season:
            raise ValueError("residual season must equal the calendar season of valid_date")
        if not math.isfinite(self.physical_p50) or not math.isfinite(self.target_mm):
            raise ValueError("residual physical_p50 and target_mm must be finite")

    @property
    def residual_mm(self) -> float:
        return self.target_mm - self.physical_p50


@dataclass(frozen=True)
class ResidualModel:
    """Training-only scaler and quantile models, retained for reproducibility."""

    scaler: StandardScaler
    estimators: tuple[GradientBoostingRegressor, ...]
    training_issue_times: tuple[datetime, ...]
    feature_names: tuple[str, ...]
    random_seed: int


def fit_residual_model(
    train: Sequence[ResidualCase], *, cutoff: datetime, seed: int = MODEL_RANDOM_SEED
) -> ResidualModel:
    """Fit residual quantiles from training cases available by ``cutoff`` only."""
    normalized_cutoff = _strict_utc(cutoff, "training cutoff")
    if not train:
        raise ValueError("residual training requires at least two training cases")
    if any(case.role != "train" for case in train):
        raise ValueError("fit_residual_model accepts only train-role cases")
    if any(case.issue_time > normalized_cutoff for case in train):
        raise ValueError("residual training case issue_time is after training cutoff")
    if len(train) < 2:
        raise ValueError("residual training requires at least two training cases")
    values = np.asarray([case.features for case in train], dtype=float)
    targets = np.asarray([case.residual_mm for case in train], dtype=float)
    scaler = StandardScaler().fit(values)
    scaled = scaler.transform(values)
    estimators = tuple(
        GradientBoostingRegressor(
            alpha=quantile,
            **MODEL_HYPERPARAMETERS,
            random_state=seed,
        ).fit(scaled, targets)
        for quantile in QUANTILES
    )
    return ResidualModel(
        scaler=scaler,
        estimators=estimators,
        training_issue_times=tuple(sorted(case.issue_time for case in train)),
        feature_names=FEATURES,
        random_seed=seed,
    )


def predict_interval(model: ResidualModel, row: ResidualCase) -> OutlookQuantiles:
    """Predict a residual interval and add it to the physical p50 baseline."""
    if not isinstance(model, ResidualModel):
        raise ValueError("predict_interval requires a ResidualModel")
    if model.feature_names != FEATURES or len(model.estimators) != len(QUANTILES):
        raise ValueError("residual model feature or quantile contract is invalid")
    scaled = model.scaler.transform(np.asarray([row.features], dtype=float))
    residuals = sorted(float(estimator.predict(scaled)[0]) for estimator in model.estimators)
    return OutlookQuantiles(
        p10=max(0.0, row.physical_p50 + residuals[0]),
        p50=max(0.0, row.physical_p50 + residuals[1]),
        p90=max(0.0, row.physical_p50 + residuals[2]),
    )


def _strict_utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be a timezone-aware UTC datetime")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{label} must use UTC")
    return value
