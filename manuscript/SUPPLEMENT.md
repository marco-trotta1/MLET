# Supplement

## S1. Reproducibility inventory

The repository stores source contracts, parsers, validators, and deterministic
artifact generators. Raw and bulky outcome archives remain outside Git.

The Phase 2 result is in `docs/results/phase2_openet_value.json`. Generated
tables and figures are in `docs/results/`.

The current AgriMet station snapshot is in
`data/outlook/agrimet_station_registry.json`. Its source receipt and historical
coverage boundary are in `docs/data/AGRIMET_STATION_REGISTRY.md`.

## S2. Phase 2 details

The Phase 2 comparison uses a common complete subset of 85 stations and 7,923
station-days. The result record stores the data manifest digest and seed.
The result remains a historical report until independent reproduction.

The deterministic generator rebuilds the Phase 2 Markdown, CSV table, and SVG
figure from the result JSON. It does not use network state or notebook state.

## S3. ETo outlook details

The ETo path evaluates only weather-driven reference ETo. It uses published
AgriMet ETos targets and archived GEFS forecast inputs. It records p10, p50,
and p90 values for leads 1 through 20.
The paired MAE comparison uses 1,000 deterministic bootstrap replicates with
issue-date and station clusters. The seed is `20260731`.

The evaluator requires a schema-v4 evidence bundle and a schema-v2 ETo target
artifact. Each case binds its forecast manifest, target artifact, source
receipts, and holdout receipt by checksum.

The full archive is not yet present. The manuscript must not report ETo skill
until the archive is complete and the result generator emits the required
tables and figures.

## S4. Deferred work

OpenET API access, CDL acquisition, soil-moisture assimilation, hybrid and
LSTM training, UI redesign, Irrigant integration, and operational promotion
are outside this manuscript draft.
