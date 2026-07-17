"""Adapters for reproducible benchmark and Idaho-outlook public sources."""

from mlet.sources.cdl import (
    CdlLayerMetadata,
    CropFraction,
    GridCell,
    aggregate_cdl,
    validate_crop_fraction,
    validate_cdl_layer_metadata,
)
from mlet.sources.gefs import (
    GefsDailyArtifactSet,
    fetch_gefs,
    materialize_gefs_daily_artifact,
    normalize_gefs_rows,
    resolve_gefs_daily_artifact,
)
from mlet.sources.openet_state import EtaAnalysis, normalize_openet_state

__all__ = [
    "CropFraction",
    "CdlLayerMetadata",
    "EtaAnalysis",
    "GefsDailyArtifactSet",
    "GridCell",
    "aggregate_cdl",
    "fetch_gefs",
    "materialize_gefs_daily_artifact",
    "normalize_gefs_rows",
    "normalize_openet_state",
    "resolve_gefs_daily_artifact",
    "validate_crop_fraction",
    "validate_cdl_layer_metadata",
]
