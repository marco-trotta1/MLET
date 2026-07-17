# MLET

Open-source machine learning evapotranspiration (MLET) is building a
reproducible, no-setup **Idaho regional evapotranspiration outlook** alongside
leakage-controlled ET research. The first public product is a 20-day,
native-weather-grid map—not a field-scale measurement, field-specific
irrigation prescription, or irrigation recommendation.

The [frozen Idaho outlook product contract](docs/outlook/PRODUCT_CONTRACT.md)
defines exactly what each map layer means, including the distinction between
forecast ETo, potential crop ET, delayed observed ETa analysis, and two
conditional ETa scenarios. The
[outlook preregistration](docs/evaluation/OUTLOOK_PREREGISTRATION.md) defines
the issue-time cutoff and the gate required before any public validation claim.

## Research questions

The current product question is whether real, issue-time-valid data can support
an auditable 20-day Idaho ETo outlook with useful uncertainty characterization.
Phase 2 answers a narrower, retrospective research question:

> Given weather data and satellite ET, does OpenET measurably improve
> daily actual-ET prediction at field-withheld flux-tower stations?

The earlier, longer-term soil-moisture research question remains:

> Given weather data, recent soil-moisture observations, and a calibrated water
> balance, does satellite evapotranspiration, specifically OpenET, measurably
> improve short-horizon soil-moisture forecasts?

Neither question authorizes a generic future actual-ET label. Phase 2 is
daily-ET evidence only; it does not validate a 20-day outlook, a soil-moisture
forecast, or an irrigation decision.

OpenET earns its place only if, for irrigated fields in the two-to-seven-day
forecast window, assimilation reduces root-zone deficit error by at least 10%
relative to a forecast-driven calibrated balance, or shifts the predicted next
irrigation timing by at least one full day toward the observed timing.

If the result does not clear that threshold, the project should report the
result as negative rather than treating a small accuracy gain as operationally
meaningful.

## Forecast Target

MLET targets root-zone soil-water deficit: the fraction of plant-available water
remaining before crop stress. Probe observations at discrete depths are intended
to be converted into a depth-weighted root-zone integral bounded by documented
field-capacity and wilting-point assumptions.

## Design Principles

- Beat strong baselines, not weak ones. Skill is measured against persistence
  and a forecast-driven calibrated water balance.
- Keep the water balance visible. Machine learning should adjust the uncertain
  terms, not replace the physical scaffold with an opaque predictor.
- Treat irrigation as a core input. Grower records are used where available;
  otherwise irrigation must be inferred from soil-moisture increases that
  precipitation cannot explain.
- Use OpenET at true latency. Satellite ET is tested as a delayed state
  assimilation signal, not as a clean real-time future driver.
- Report uncertainty honestly. Forecasts should produce calibrated predictive
  intervals, not only point estimates.

## Planned Inputs

MLET is designed around daily, field-keyed records assembled from:

- recent in-situ soil-moisture observations;
- tower evapotranspiration where available for ET ground truth;
- reference evapotranspiration from gridded meteorology;
- precipitation, temperature, humidity, vapor pressure deficit, solar radiation,
  and wind;
- vegetation indices;
- OpenET actual evapotranspiration, included only at realistic latency;
- numerical weather forecasts;
- irrigation records or temporally valid inferred irrigation events;
- static field attributes such as soil hydraulic limits, crop, and rooting
  depth.

The field network size, date range, number of irrigated field-seasons, and tower
coverage are load-bearing metadata and should be recorded before modeling
claims are made.

## Modeling Approach

The intended model is a differentiable version of the FAO-56 dual-coefficient
water balance. The physical scaffold tracks the daily water balance while small
learned functions estimate the terms that fixed coefficients handle poorly:

- the water-stress coefficient that controls how a stressed crop throttles water
  use;
- the deep-percolation term that controls drainage past the root zone.

The model should condition on physical field attributes, not arbitrary field
identifiers, so withheld-field evaluation remains meaningful.

This repository currently vendors `pyfao56` as the FAO-56 implementation
foundation. See `vendor/pyfao56/UPSTREAM.md` for the upstream source, version,
commit, and local scope.

## Evaluation Plan

Evaluation should be pre-registered before running the OpenET comparison. The
pre-registration should freeze:

- the OpenET hypothesis;
- the 10% deficit-error and one-day irrigation-timing thresholds;
- field-withheld and time-withheld splits;
- baseline definitions;
- leakage checks;
- metrics and stratifications.

Required comparisons:

- persistence baseline;
- forecast-driven calibrated water balance;
- full model with OpenET assimilation;
- matching model without OpenET assimilation.

Primary reporting should focus on:

- two-to-seven-day root-zone deficit skill over the floor;
- next-irrigation timing error in days;
- predictive interval coverage;
- continuous ranked probability score;
- stratified OpenET value by irrigated versus rainfed fields and by crop.

## Outputs

The planned system should produce:

- field-level soil-water status;
- two-to-seven-day forecast trajectories with predictive intervals;
- irrigation threshold and days-until-water estimates;
- performance relative to the baseline floor;
- data freshness timestamps;
- machine-readable forecast outputs;
- notebooks or scripts that reproduce published figures;
- a frozen benchmark with field-withheld splits and a pre-registered analysis
  plan.

## Current Repository Status

This repository contains a reproducible Phase 2 daily-ET baseline and the
frozen product and evaluation contracts for the Idaho outlook. It is not yet a
validated 20-day forecasting product.

Present contents:

- top-level project README;
- vendored `pyfao56` source snapshot;
- upstream provenance for the vendored dependency;
- reproducible public OpenET/flux/gridMET ingestion and checksum verification;
- a typed ET loader, transparent baselines, leakage-controlled evaluation, and
  a pre-registered Phase 2 daily-ET comparison;
- [data provenance and coverage notes](docs/data/DATA_CARD.md),
  [the frozen evaluation design](docs/evaluation/PREREGISTRATION.md), and
  [generated Phase 2 results](docs/results/phase2_openet_value.md);
- the [Idaho outlook product contract](docs/outlook/PRODUCT_CONTRACT.md),
  [outlook preregistration](docs/evaluation/OUTLOOK_PREREGISTRATION.md), and
  [operational source registry](data/outlook/source_registry.json).

Phase 2 finds that, on the 85-station weather-complete public subset, the
OpenET-inclusive model reduced field-withheld daily-ET MAE by 43.4% relative to
the best OpenET-free baseline (95% CI 0.399–0.911 mm); this is daily-ET evidence
only, not validation of the Idaho outlook, soil-moisture forecasts, or
irrigation decisions.

Not yet present:

- a reproducible operational outlook build;
- preregistered 20-day hindcast results;
- a promoted or validated public forecast map;
- model-training code or OpenET assimilation into a soil-moisture water balance.

## Non-serving residual-model experiment

The [frozen residual-model protocol](docs/evaluation/OUTLOOK_RESIDUAL_MODEL_PROTOCOL.md)
adds a deliberately isolated advanced-ML proving ground. It trains quantile
residuals only beside the physical well-watered ETa scenario, using frozen
geographic-and-seasonal holdouts, chronological train/gap/calibration/gap/test
partitions, issue-time feature availability, finite-sample conformal intervals,
and recorded package/seed/data hashes.
It cannot change the outlook artifact, map, Helios, or Irrigant input, and it
always writes `promotion: false` for separately trusted external review.

```bash
python3 -m mlet evaluate-outlook-residual \
  --cases examples/outlook/hindcast_cases.json \
  --out /private/tmp/idaho_outlook_residual.md
```

That bundled input is a visibly non-scientific software fixture. Archive-local
checksums for Task 8 cases and feature receipts are useful replay diagnostics,
but are not independent provenance: an archive author can supply both the rows
and receipts. An external archive-reconstruction authority must rebuild the
rows from raw source artifacts before separate release review; this repository
always emits `promotion: false` and `external_release_eligible: false`.

## Static research-candidate map

`mlet publish-outlook` renders a standalone `index.html`, `outlook.geojson`,
`summary.json`, and `serve-contract.json` from a verified immutable
`OUTPUT_ROOT/RUN_ID` handle. It is intentionally useful for inspecting the
native weather-grid quantities and their uncertainty without a web-service or
package setup, but it always returns exit code `1`: the output is a **research
candidate**, with `promotion: false` and `validation_status:
"validation_pending"`.

```bash
python3 -m mlet publish-outlook --run OUTPUT_ROOT/RUN_ID
```

The renderer reads input only through the descriptor-anchored run reader and
does not alter the immutable generation. It stages candidate artifacts below a
trusted output root and atomically exposes a new sibling candidate directory;
it never overwrites one. Its map labels keep ETo outlook, potential
crop ET, the dated ETa analysis, and the two conditional ETa scenarios
separate. A weather-grid reference point, when included by the source contract,
is not a field boundary. The candidate summary uses an explicitly labelled
equal-cell descriptive mean—not a statewide area-weighted statistic—until
source-grid cell areas are carried in the serving contract.

Fixture input produces a conspicuous non-scientific software-fixture map. It is
never a forecast claim or scientific evidence. For qualifying archived data,
only the separately trusted external release authority described in the outlook
preregistration may publish a promoted product; the MLET evaluator and map
renderer have no local promotion or validation path.

## Development Notes

Keep new work reproducible and auditable:

- do not commit raw private field data;
- prefer manifests, checksums, and scripts over manual data drops;
- enforce temporal cutoffs before forecast generation;
- keep negative results visible when thresholds are not met;
- document assumptions before they enter the model.

## Source Brief

This README summarizes the project direction from the "Forecasting Soil
Moisture" project brief by Marco Trotta and aligns it with the repository's
current scaffold.

## Phase 1: ET time-series validation

The first MLET-owned component is a local, zero-dependency validator for daily,
site-keyed evapotranspiration CSV files. It checks structure and types and
reports contents honestly; it does not train, score, or make scientific claims.

Install and run:

```bash
python3 -m pip install -e .
mlet validate-csv examples/et_timeseries_template.csv
# or:
python3 -m mlet validate-csv examples/et_timeseries_template.csv
```

The expected CSV columns are `date` (YYYY-MM-DD), `site_id`, `openet_et_mm`
(required), and optional `eto_mm`, `ndvi`, `measured_et_mm`. A file with no
measured ET validates structurally but reports `has_measured_labels: false`.

See `docs/superpowers/specs/2026-06-28-mlet-phase1-et-csv-validator-design.md`
for the full data contract and design.
