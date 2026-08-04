# Data availability

The Phase 2 source manifest is in [`../data/manifest.json`](../data/manifest.json).
The machine-readable Phase 2 result is in
[`../docs/results/phase2_openet_value.json`](../docs/results/phase2_openet_value.json).

The public AgriMet station registry snapshot is in
[`../data/outlook/agrimet_station_registry.json`](../data/outlook/agrimet_station_registry.json).
Its source hashes and current-only limitation are in
[`../docs/data/AGRIMET_STATION_REGISTRY.md`](../docs/data/AGRIMET_STATION_REGISTRY.md).

The ETo target source is the USBR AgriMet historical archive. The forecast
source is the NOAA GEFS reforecast archive. A complete outcome archive is not
yet included. The verified weekly GEFS layout uses Wednesday 00Z issues from
2013-01-02 through 2019-12-25, 11 members, and lead days through 35. A full
2019-07-03 availability survey found 187 of 187 required objects. Do not state
that the full ETo data set is available until the raw source receipts,
historical station records, and checksums are published with the hindcast
result.

OpenET, flux, and gridMET benchmark sources remain subject to their recorded
provider terms. See the data card for source-specific attribution.
