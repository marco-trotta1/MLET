# MLET

Open-source machine learning evapotranspiration (MLET) is a soil-moisture
forecasting project built around a calibrated water balance, weather forecasts,
in-situ observations, and satellite evapotranspiration.

The goal is practical: forecast root-zone soil-water deficit far enough ahead
to support irrigation timing decisions, with the strongest emphasis on the
two-to-seven-day horizon.

## Research Question

Given weather data, recent soil-moisture observations, and a calibrated water
balance, does satellite evapotranspiration, specifically OpenET, measurably
improve short-horizon soil-moisture forecasts?

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

This repository is an early scaffold, not a complete forecasting product.

Present contents:

- top-level project README;
- vendored `pyfao56` source snapshot;
- upstream provenance for the vendored dependency;
- reproducible public OpenET/flux/gridMET ingestion and checksum verification;
- a typed ET loader, transparent baselines, leakage-controlled evaluation, and
  a pre-registered Phase 2 daily-ET comparison;
- [data provenance and coverage notes](docs/data/DATA_CARD.md),
  [the frozen evaluation design](docs/evaluation/PREREGISTRATION.md), and
  [generated Phase 2 results](docs/results/phase2_openet_value.md).

Phase 2 finds that, on the 85-station weather-complete public subset, the
OpenET-inclusive model reduced field-withheld daily-ET MAE by 43.4% relative to
the best OpenET-free baseline (95% CI 0.399–0.911 mm); this is daily-ET evidence
only, not validation of soil-moisture forecasts or irrigation decisions.

Not yet present:

- model-training code;
- OpenET assimilation into a soil-moisture water balance;
- dashboard or forecast output files.

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
