# Data availability

The Phase 2 source manifest is at ../data/manifest.json. The machine-readable
Phase 2 result is at ../docs/results/phase2_openet_value.json.

The public AgriMet station registry is at
../data/outlook/agrimet_station_registry.json. Historical station evidence for
the 19 acquired stations is at
../data/outlook/agrimet_station_history_historical_pages.json. The map audit
is at ../docs/data/AGRIMET_HISTORICAL_MAP_AUDIT.md.

The retrospective target is USBR AgriMet grass-reference evapotranspiration
(ETos). The forecast source is the NOAA Global Ensemble Forecast System
version 12 (GEFSv12) reforecast archive. OpenET and gridMET remain separate
benchmark sources. Provider terms and source receipts remain part of the
repository evidence record.

The full outcome archive is not included. The verified weekly layout uses
Wednesday 00Z (00:00 UTC) issues from 2013-01-02 through 2019-12-25, 11
members, and lead days through 35. The 2019-07-03 feasibility archive contains
187 of 187 required GEFS objects and one decoded version-2 artifact. It has
one BOII station case at grid point 43.50:-116.00, fold 2, with 20 target
records. It has one bootstrap cluster, so support is below the frozen minimum
of 30 targets per cell. Empirical p10-to-p90 coverage is 0.25 against the
nominal target of 0.80. Mean band width is 1.453 mm/day. No paired confidence
interval is reported.

The BOII timing fields are separate. The source issue time is
2019-07-03T00:00:00Z. The archive availability time is
2026-08-04T18:08:54.243122Z. The latter does not show public operational
availability in 2019.

Do not describe the full reference-ETo hindcast as available until every issue
receipt, target record, checksum, support cell, and release-review result is
published with the hindcast.
