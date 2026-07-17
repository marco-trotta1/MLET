"""Adapters for reproducible benchmark and Idaho-outlook public sources."""

from mlet.sources.cdl import CdlLayerMetadata, CropFraction, GridCell, aggregate_cdl
from mlet.sources.gefs import (
    fetch_gefs,
    materialize_gefs_daily_artifact,
    normalize_gefs_rows,
)
from mlet.sources.openet_state import EtaAnalysis, normalize_openet_state

__all__ = [
    "CropFraction",
    "CdlLayerMetadata",
    "EtaAnalysis",
    "GridCell",
    "aggregate_cdl",
    "fetch_gefs",
    "materialize_gefs_daily_artifact",
    "normalize_gefs_rows",
    "normalize_openet_state",
]
