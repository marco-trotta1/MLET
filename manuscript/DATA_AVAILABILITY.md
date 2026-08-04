# Data availability

The Phase 2 source manifest is in [`../data/manifest.json`](../data/manifest.json).
The machine-readable Phase 2 result is in
[`../docs/results/phase2_openet_value.json`](../docs/results/phase2_openet_value.json).

The public AgriMet station registry snapshot is in
[`../data/outlook/agrimet_station_registry.json`](../data/outlook/agrimet_station_registry.json).
Historical station evidence for the acquired 19 stations is in
[`../data/outlook/agrimet_station_history_historical_pages.json`](../data/outlook/agrimet_station_history_historical_pages.json).
The map audit is in
[`../docs/data/AGRIMET_HISTORICAL_MAP_AUDIT.md`](../docs/data/AGRIMET_HISTORICAL_MAP_AUDIT.md).

The ETo target source is the USBR AgriMet historical archive. The forecast
source is the NOAA GEFS reforecast archive. A complete outcome archive is not
yet included. The verified weekly GEFS layout uses Wednesday 00Z issues from
2013-01-02 through 2019-12-25, 11 members, and lead days through 35. A full
The 2019-07-03 feasibility archive contains 187 of 187 required GEFS objects,
one decoded version-2 artifact, and one BOII target case. Do not state that the
full ETo data set is available until all issue receipts, target records, and
checksums are published with the hindcast result.

OpenET, flux, and gridMET benchmark sources remain subject to their recorded
provider terms. See the data card for source-specific attribution.
