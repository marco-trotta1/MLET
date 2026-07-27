"""Non-scientific deterministic checks for the frozen train-only scaler artifact."""

import json
from datetime import datetime, timezone

import numpy as np
import pytest

from mlet.outlook.residual_model import FEATURES
from mlet.outlook.scaler_artifact import (
    ScalerArtifact,
    apply_scaler,
    artifact_sha256,
    read_scaler_artifact,
    write_scaler_artifact,
)

CUTOFF = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _artifact() -> ScalerArtifact:
    return ScalerArtifact(
        feature_names=FEATURES,
        mean=tuple(float(i) for i in range(len(FEATURES))),
        scale=tuple(1.0 + i for i in range(len(FEATURES))),
        n_training_cases=64,
        training_cutoff=CUTOFF.isoformat(),
    )


def test_round_trip_is_lossless(tmp_path) -> None:
    path = write_scaler_artifact(_artifact(), tmp_path / "scaler.json")
    assert read_scaler_artifact(path) == _artifact()


def test_serialised_form_is_plain_reviewable_json(tmp_path) -> None:
    path = write_scaler_artifact(_artifact(), tmp_path / "scaler.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["feature_names"] == list(FEATURES)
    assert payload["n_training_cases"] == 64
    assert payload["training_cutoff"] == CUTOFF.isoformat()


def test_hash_is_stable_and_sensitive(tmp_path) -> None:
    first = artifact_sha256(_artifact())
    assert first == artifact_sha256(_artifact())
    perturbed = ScalerArtifact(
        feature_names=FEATURES,
        mean=_artifact().mean,
        scale=tuple(value + 1e-9 for value in _artifact().scale),
        n_training_cases=64,
        training_cutoff=CUTOFF.isoformat(),
    )
    assert artifact_sha256(perturbed) != first


def test_zero_scale_is_rejected() -> None:
    """A constant training feature would divide by zero at prediction time."""
    with pytest.raises(ValueError, match="scale must be positive"):
        ScalerArtifact(
            feature_names=FEATURES,
            mean=tuple(0.0 for _ in FEATURES),
            scale=tuple(0.0 for _ in FEATURES),
            n_training_cases=64,
            training_cutoff=CUTOFF.isoformat(),
        )


def test_feature_name_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="must name FEATURES in order"):
        ScalerArtifact(
            feature_names=tuple(reversed(FEATURES)),
            mean=tuple(0.0 for _ in FEATURES),
            scale=tuple(1.0 for _ in FEATURES),
            n_training_cases=64,
            training_cutoff=CUTOFF.isoformat(),
        )


def test_apply_scaler_matches_the_standard_transform() -> None:
    artifact = _artifact()
    features = tuple(float(2 * i) for i in range(len(FEATURES)))
    expected = (np.asarray(features) - np.asarray(artifact.mean)) / np.asarray(artifact.scale)
    assert np.allclose(apply_scaler(artifact, features), expected)


def test_frozen_artifact_reproduces_the_live_scaler_transform() -> None:
    """Round-tripping through JSON must not change a single prediction."""
    from mlet.outlook.residual_model import (
        fit_residual_model,
        predict_interval,
        scaler_artifact_from_model,
    )
    from tests.test_outlook_residual_model import _training_cases

    train = _training_cases()
    model = fit_residual_model(train, cutoff=CUTOFF)
    artifact = scaler_artifact_from_model(
        model,
        n_training_cases=len(train),
        training_cutoff=CUTOFF,
    )

    live = model.scaler.transform(np.asarray([train[0].features], dtype=float))
    frozen = apply_scaler(artifact, train[0].features).reshape(1, -1)
    assert np.allclose(live, frozen, rtol=0, atol=1e-12)

    interval = predict_interval(model, train[0], scaler=artifact)
    assert interval.p10 <= interval.p50 <= interval.p90
