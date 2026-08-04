# 2019-07-03 feasibility evidence

This record binds one real GEFS issue to one independent AgriMet ETos target.

## GEFS transfer

- Issue: `2019-07-03T00:00:00Z`
- Objects: 187 of 187
- Raw bytes: 8,289,206,079
- Runtime: 2,701.632 seconds
- Mean throughput: 3.068222 MB/s
- Peak disk use: 8,547,991,552 bytes
- Minimum free disk: 717,383,708,672 bytes
- Raw receipt SHA-256: `7561a07fc463add0c39b75b6b247070b647451ed7b795efa9c88d800c477592e`
- Transfer benchmark: `data/outlook/gefs_reforecast_20190703_transfer_benchmark.json`
- Per-object metadata: `data/outlook/gefs_reforecast_20190703_transfer_receipt.json`

Transfer runtime and throughput are single-run measurements. No repeat-run
uncertainty is estimated.

The raw GRIB files remain in the external evidence root
`MLET Evidence/gefs-v12-20190703`.

## GEFS decode

- Artifact schema: version 2
- Rows: 42,900
- Grid cells: 195
- Members: 11
- Valid dates: 20
- Decode runtime: 80.323 seconds
- Artifact SHA-256: `154e88317fe9aa6bb7b31595e5cbdd149735ffc92acdfc7ed55d7b68e49d901c`
- Normalized SHA-256: `c9771c147204f07efb2c5b66122b25e7231d724ff8e2ef7cc5ebcd4f4e416fa8`
- Artifact receipt: `data/outlook/gefs_reforecast_20190703_artifact_receipt.json`
- Decoder lock: `requirements-gefs.lock`

Decode runtime is a single-run measurement. No repeat-run uncertainty is
estimated.

The real ETo candidate is `research_candidate`, with evaluation pending and
promotion disabled. The candidate SHA-256 is
`9476bab0be5cd879d1912a40c73ff5d694d9ae95502d67e8f6d82ee2426adb3b`.

## AgriMet target

- Station: `BOII`
- Target dates: 2019-07-03 through 2019-07-22
- Target rows: 20
- Exclusions: 0
- Grid match: `43.50:-116.00`
- Distance: 18.10119132115406 km
- Maximum allowed distance: 50.0 km
- Station history: `data/outlook/agrimet_station_history_boii.json`
- Station history evidence manifest: `data/outlook/agrimet_station_history_boii_evidence.json`
- Feasibility receipt: `data/outlook/agrimet_boii_feasibility.json`
- Schema-v2 target: `data/outlook/eto_feasibility_targets/targets/issue-20190703-station-BOII-season-JJA-fold-4.json`
- Schema-v4 evidence: `data/outlook/eto_feasibility_archive/evidence.json`
- Target SHA-256: `7aabbf02699745d7051bc09d7c00bd59e969abbcf639d391728086fd817d9751`
- Evidence SHA-256: `890555ea6e0f912655fbdcbb7cd1291c019ce9545e21407f3a9432f1582bba38`

The station history uses five dated map snapshots with identical BOII
coordinates and one archived station page with elevation. It is bracketed
archival location evidence. It is not a complete USBR relocation ledger. The
source-normalized target artifact remains schema version 1. The derived target
artifact is schema version 2 and binds the forecast run and source receipt.
The evidence bundle is schema version 4 and remains evaluation pending.

## Full-plan gate

- Issues: 365
- Objects: 68,255
- Plan SHA-256: `49c6ae854cc17d393f9283bdc299be6628ef152b4a5879b299e20ea4b290e250`
- Estimated raw bytes: 3,025,560,218,835
- Status: plan complete, acquisition pending temporary project storage

The issue plan SHA-256 is
`ded7ebb2d449b1d9163368c679961eccccc4c6b0c0c9deb8b8a8f37d79a2a914`.
The complete plan is `data/outlook/gefs_reforecast_acquisition_plan.json`.

## Independent Phase 2 record

The checksum-verified independent reproduction is recorded in
`docs/results/phase2_openet_independent_reproduction_receipt.json`.
All comparison checks against the committed result are true.

The feasibility evidence passes byte, source, target, issue-time, fold, and
season checks for one real station case. The scientific evaluation remains
incomplete because it lacks the other folds and seasons. No full ETo
performance result is committed.
