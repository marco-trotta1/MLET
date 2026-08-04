"""Stable, reproducible contracts for the Idaho regional ET outlook."""

from mlet.outlook.contracts import (
    OutlookDay,
    OutlookQuantiles,
    SourceRecord,
    WeatherMember,
)
from mlet.outlook.manifest import RunManifest, build_manifest
from mlet.outlook.eto_contract import (
    EtoCandidateContract,
    VALIDATION_SCOPE,
    load_eto_candidate,
    validate_eto_candidate_payload,
)
from mlet.outlook.hindcast import VALIDATION_LAYERS


def __getattr__(name: str) -> object:
    """Load archive exports only when a caller requests them."""
    if name == "build_eto_hindcast_archive":
        from mlet.outlook.archive import build_eto_hindcast_archive

        return build_eto_hindcast_archive
    if name == "evaluate_eto_hindcast_evidence":
        from mlet.outlook.hindcast import evaluate_eto_hindcast_evidence

        return evaluate_eto_hindcast_evidence
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "OutlookDay",
    "OutlookQuantiles",
    "RunManifest",
    "SourceRecord",
    "WeatherMember",
    "build_manifest",
    "EtoCandidateContract",
    "VALIDATION_SCOPE",
    "load_eto_candidate",
    "validate_eto_candidate_payload",
    "build_eto_hindcast_archive",
    "VALIDATION_LAYERS",
    "evaluate_eto_hindcast_evidence",
]
