"""Frozen, train-only feature normalisation, serialised as reviewable JSON.

Adapted from neuralhydrology (v1.13.0, BSD-3-Clause), which fits normalisation on
the training split, writes it to ``train_data/train_data_scaler.yml``, and
requires it as an input when evaluating. That makes normalisation-statistics
leakage structurally impossible instead of a review item.

Serialised as JSON rather than pickle deliberately: a scaler is a mean vector and
a scale vector, and JSON is diffable, reviewable, stable across scikit-learn
versions, and does not execute code on load.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from mlet.outlook.residual_model import ResidualModel


@dataclass(frozen=True)
class ScalerArtifact:
    """Training-split normalisation statistics, one entry per feature."""

    feature_names: tuple[str, ...]
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    n_training_cases: int
    training_cutoff: str

    def __post_init__(self) -> None:
        from mlet.outlook.residual_model import FEATURES

        if tuple(self.feature_names) != FEATURES:
            raise ValueError("scaler feature_names must name FEATURES in order")
        if len(self.mean) != len(FEATURES) or len(self.scale) != len(FEATURES):
            raise ValueError("scaler mean and scale must have one entry per feature")
        if not all(math.isfinite(value) for value in self.mean + self.scale):
            raise ValueError("scaler mean and scale must be finite")
        if any(value <= 0 for value in self.scale):
            raise ValueError(
                "scaler scale must be positive; a zero scale means a training "
                "feature was constant and prediction would divide by zero"
            )
        if self.n_training_cases < 2:
            raise ValueError("scaler requires at least two training cases")
        try:
            cutoff = datetime.fromisoformat(self.training_cutoff)
        except ValueError as error:
            raise ValueError("scaler training_cutoff must be ISO-8601 text") from error
        if cutoff.tzinfo is None or cutoff.utcoffset() != timezone.utc.utcoffset(cutoff):
            raise ValueError("scaler training_cutoff must be ISO-8601 UTC text")


def scaler_artifact_from_model(
    model: ResidualModel, *, n_training_cases: int, training_cutoff: datetime
) -> ScalerArtifact:
    """Extract the serialisable statistics from a fitted ``ResidualModel``."""
    return ScalerArtifact(
        feature_names=tuple(model.feature_names),
        mean=tuple(float(value) for value in model.scaler.mean_),
        scale=tuple(float(value) for value in model.scaler.scale_),
        n_training_cases=int(n_training_cases),
        training_cutoff=training_cutoff.isoformat(),
    )


def _canonical_json(artifact: ScalerArtifact) -> str:
    payload = asdict(artifact)
    payload["feature_names"] = list(artifact.feature_names)
    payload["mean"] = list(artifact.mean)
    payload["scale"] = list(artifact.scale)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def write_scaler_artifact(artifact: ScalerArtifact, destination: Path) -> Path:
    """Write the artifact as indented JSON and return the path."""
    destination = Path(destination)
    payload = json.loads(_canonical_json(artifact))
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def read_scaler_artifact(path: Path) -> ScalerArtifact:
    """Read an artifact, validating it through ``ScalerArtifact.__post_init__``."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ScalerArtifact(
        feature_names=tuple(payload["feature_names"]),
        mean=tuple(float(value) for value in payload["mean"]),
        scale=tuple(float(value) for value in payload["scale"]),
        n_training_cases=int(payload["n_training_cases"]),
        training_cutoff=str(payload["training_cutoff"]),
    )


def artifact_sha256(artifact: ScalerArtifact) -> str:
    """Stable content hash over the canonical JSON form."""
    return hashlib.sha256(_canonical_json(artifact).encode("utf-8")).hexdigest()


def apply_scaler(artifact: ScalerArtifact, features: Sequence[float]) -> np.ndarray:
    """Standardise one feature row using the frozen training statistics."""
    values = np.asarray(features, dtype=float)
    if values.shape != (len(artifact.feature_names),):
        raise ValueError("feature row length must match the scaler feature count")
    return (values - np.asarray(artifact.mean)) / np.asarray(artifact.scale)
