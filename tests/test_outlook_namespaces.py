"""Non-scientific deterministic checks for feature namespace provenance rules."""

import pytest

from mlet.outlook import namespaces
from mlet.outlook.residual_model import FEATURES


def test_every_feature_has_exactly_one_namespace() -> None:
    assert tuple(namespaces.FEATURE_NAMESPACES) == FEATURES
    assert set(namespaces.FEATURE_NAMESPACES.values()) <= {
        namespaces.Namespace.STATIC,
        namespaces.Namespace.HINDCAST,
        namespaces.Namespace.FORECAST,
    }


def test_hindcast_namespace_admits_observations_only() -> None:
    """The leakage class this task exists to block."""
    allowed = namespaces.ALLOWED_PROVENANCE[namespaces.Namespace.HINDCAST]
    assert allowed == frozenset({namespaces.ProvenanceKind.OBSERVATION})
    assert namespaces.ProvenanceKind.FORECAST_PRODUCT not in allowed


def _valid_provenance() -> tuple[tuple[str, str], ...]:
    return (
        ("lead_day", namespaces.ProvenanceKind.STRUCTURAL),
        ("eto_p50", namespaces.ProvenanceKind.FORECAST_PRODUCT),
        ("eto_spread", namespaces.ProvenanceKind.FORECAST_PRODUCT),
        ("precip_p50", namespaces.ProvenanceKind.FORECAST_PRODUCT),
        ("crop_fraction", namespaces.ProvenanceKind.STATIC_ATTRIBUTE),
        ("kc", namespaces.ProvenanceKind.STATIC_ATTRIBUTE),
        ("taw_mm", namespaces.ProvenanceKind.STATIC_ATTRIBUTE),
        ("initial_depletion_mm", namespaces.ProvenanceKind.OBSERVATION),
        ("eta_analysis_age_days", namespaces.ProvenanceKind.OBSERVATION),
    )


def test_valid_provenance_is_accepted() -> None:
    namespaces.validate_feature_provenance(_valid_provenance())


def test_forecast_sourced_hindcast_feature_is_rejected() -> None:
    """The leakage this task exists to block: a forecast posing as observed state."""
    provenance = tuple(
        (
            name,
            namespaces.ProvenanceKind.FORECAST_PRODUCT
            if name == "initial_depletion_mm"
            else kind,
        )
        for name, kind in _valid_provenance()
    )
    with pytest.raises(ValueError, match="initial_depletion_mm"):
        namespaces.validate_feature_provenance(provenance)


def test_observation_sourced_forecast_feature_is_rejected() -> None:
    provenance = tuple(
        (name, namespaces.ProvenanceKind.OBSERVATION if name == "eto_p50" else kind)
        for name, kind in _valid_provenance()
    )
    with pytest.raises(ValueError, match="eto_p50"):
        namespaces.validate_feature_provenance(provenance)


def test_missing_or_reordered_features_are_rejected() -> None:
    with pytest.raises(ValueError, match="must name FEATURES in order"):
        namespaces.validate_feature_provenance(_valid_provenance()[:-1])
    with pytest.raises(ValueError, match="must name FEATURES in order"):
        namespaces.validate_feature_provenance(tuple(reversed(_valid_provenance())))
