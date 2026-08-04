"""Adapters for reproducible benchmark and Idaho-outlook public sources."""

from mlet.sources.agrimet_station_history import (
    AgriMetStationHistoryRegistry,
    AgriMetStationLocation,
    load_agrimet_station_history_registry,
    resolve_agrimet_station_location,
)
from mlet.sources.agrimet import (
    AgriMetEtosObservation,
    AgriMetGridMatch,
    agrimet_etos_archive_uri,
    map_agrimet_station_to_grid,
    normalize_agrimet_etos_rows,
)
from mlet.sources.agrimet_station_registry import (
    AgriMetStationRecord,
    AgriMetStationRegistrySnapshot,
    load_agrimet_station_registry,
    stations_for_state,
)
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
    serialize_gefs_daily_artifact,
)
from mlet.sources.gefs_reforecast_uri import (
    gefs_reforecast_member_ids,
    gefs_reforecast_object_uri,
)
from mlet.sources.openet_state import EtaAnalysis, normalize_openet_state

__all__ = [
    "AgriMetStationHistoryRegistry",
    "AgriMetStationLocation",
    "AgriMetEtosObservation",
    "AgriMetGridMatch",
    "AgriMetStationRecord",
    "AgriMetStationRegistrySnapshot",
    "CdlLayerMetadata",
    "CropFraction",
    "EtaAnalysis",
    "GefsDailyArtifactSet",
    "GridCell",
    "aggregate_cdl",
    "agrimet_etos_archive_uri",
    "fetch_gefs",
    "gefs_reforecast_member_ids",
    "gefs_reforecast_object_uri",
    "load_agrimet_station_history_registry",
    "load_agrimet_station_registry",
    "map_agrimet_station_to_grid",
    "materialize_gefs_daily_artifact",
    "normalize_gefs_rows",
    "normalize_agrimet_etos_rows",
    "normalize_openet_state",
    "resolve_agrimet_station_location",
    "stations_for_state",
    "resolve_gefs_daily_artifact",
    "serialize_gefs_daily_artifact",
    "validate_crop_fraction",
    "validate_cdl_layer_metadata",
]
