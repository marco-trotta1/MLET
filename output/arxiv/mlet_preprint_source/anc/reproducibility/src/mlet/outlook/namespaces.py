"""Feature namespace and provenance contract for issue-time-valid features.

Adapted from the neuralhydrology config-level separation of
``static_attributes`` / ``hindcast_inputs`` / ``forecast_inputs``
(v1.13.0, BSD-3-Clause). MLET adds provenance kind, because availability by
issue time is necessary but not sufficient: a forecast issued before issue time
passes an availability check while still carrying information the observation
record does not have.

The load-bearing rule is that the hindcast namespace admits observations only.
``initial_depletion_mm`` is the state the outlook integrates forward from; if it
could be sourced from a forecast product, the leakage-control argument in
docs/evaluation/OUTLOOK_PREREGISTRATION.md would not hold.
"""

from __future__ import annotations


class Namespace:
    """Input namespaces, mirroring neuralhydrology's config-level separation."""

    STATIC = "static"
    HINDCAST = "hindcast"
    FORECAST = "forecast"


class ProvenanceKind:
    """Where a feature's value actually came from."""

    STATIC_ATTRIBUTE = "static_attribute"
    OBSERVATION = "observation"
    FORECAST_PRODUCT = "forecast_product"
    STRUCTURAL = "structural"


#: Namespace of each feature in ``mlet.outlook.residual_model.FEATURES``, in the
#: same order. Keep this in sync with FEATURES; the tests assert the ordering.
FEATURE_NAMESPACES: dict[str, str] = {
    "lead_day": Namespace.STATIC,
    "eto_p50": Namespace.FORECAST,
    "eto_spread": Namespace.FORECAST,
    "precip_p50": Namespace.FORECAST,
    "crop_fraction": Namespace.STATIC,
    "kc": Namespace.STATIC,
    "taw_mm": Namespace.STATIC,
    "initial_depletion_mm": Namespace.HINDCAST,
    "eta_analysis_age_days": Namespace.HINDCAST,
}

#: Provenance kinds each namespace admits.
ALLOWED_PROVENANCE: dict[str, frozenset[str]] = {
    Namespace.STATIC: frozenset(
        {ProvenanceKind.STATIC_ATTRIBUTE, ProvenanceKind.STRUCTURAL}
    ),
    Namespace.HINDCAST: frozenset({ProvenanceKind.OBSERVATION}),
    Namespace.FORECAST: frozenset({ProvenanceKind.FORECAST_PRODUCT}),
}

_EXPECTED_PROVENANCE: dict[str, str] = {
    "lead_day": ProvenanceKind.STRUCTURAL,
    "eto_p50": ProvenanceKind.FORECAST_PRODUCT,
    "eto_spread": ProvenanceKind.FORECAST_PRODUCT,
    "precip_p50": ProvenanceKind.FORECAST_PRODUCT,
    "crop_fraction": ProvenanceKind.STATIC_ATTRIBUTE,
    "kc": ProvenanceKind.STATIC_ATTRIBUTE,
    "taw_mm": ProvenanceKind.STATIC_ATTRIBUTE,
    "initial_depletion_mm": ProvenanceKind.OBSERVATION,
    "eta_analysis_age_days": ProvenanceKind.OBSERVATION,
}


def validate_feature_provenance(provenance: tuple[tuple[str, str], ...]) -> None:
    """Raise ``ValueError`` unless every feature's provenance suits its namespace.

    ``provenance`` is a tuple of ``(feature_name, provenance_kind)`` pairs naming
    every entry of ``FEATURES`` exactly once, in order.
    """
    from mlet.outlook.residual_model import FEATURES

    names = tuple(name for name, _kind in provenance)
    if names != FEATURES:
        raise ValueError("residual feature provenance must name FEATURES in order")
    for name, kind in provenance:
        namespace = FEATURE_NAMESPACES[name]
        allowed = ALLOWED_PROVENANCE[namespace]
        if kind not in allowed:
            raise ValueError(
                f"feature {name} is in the {namespace} namespace, which admits "
                f"{sorted(allowed)}, but its provenance is {kind!r}"
            )
        expected = _EXPECTED_PROVENANCE[name]
        if kind != expected:
            raise ValueError(
                f"feature {name} must declare provenance {expected!r}, not {kind!r}"
            )
