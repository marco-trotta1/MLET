# Phase 2 pre-registration: OpenET-value baseline

**Frozen:** 2026-07-13  
**Seed:** `20260713`

## Reduced public-data question

Against eddy-covariance tower ET (energy-balance-corrected) as ground truth,
does including OpenET reduce daily actual-ET prediction error relative to the
best OpenET-free baseline (reference ET + weather + season), on
field-withheld stations, by at least 10%?

## Hypotheses

- **H1 (baseline ordering).** OpenET ensemble ET predicts daily EBC tower ET
  with lower pooled MAE than (a) a persistence baseline and (b) a static
  crop-coefficient (ETo-ratio) baseline, on the field-withheld split.
- **H2 (OpenET value — primary).** An OpenET-inclusive model (M3) achieves at
  least 10% lower field-withheld pooled MAE than the best OpenET-free baseline
  (B1 or B2), with a station-blocked bootstrap 95% CI on the MAE reduction that
  excludes 0.
- **H2-strat.** The H2 effect is reported separately for croplands and
  non-croplands; OpenET is expected to help most on irrigated croplands.

## Decision rule

If H2 clears **both** the at-least-10% point reduction and a CI excluding 0 on
the field-withheld split, report **OpenET adds daily-ET value** and proceed to
Phase 3 assimilation design. If the reduction is positive but below 10%, or the
CI includes 0, report a **negative/insufficient** result explicitly. Do not
advance to assimilation on a sub-threshold gain.

## Frozen design

- Models: B0 Persistence; B1 CropCoefficient; B2 WeatherRidge; M1
  OpenETDirect; M2 OpenETRecal; M3 OpenETRidge.
- Field-withheld evaluation: `k=10`, seed `20260713`; no station appears in
  both training and testing in a fold. Fitted standardization and all learned
  parameters use training rows only.
- Parallel time-withheld evaluation: train through `2018-12-31`; test from
  `2019-01-01`; it is descriptive, not the primary decision split.
- Primary metric: pooled MAE on field-withheld test rows. Secondary metrics:
  RMSE and signed bias.
- Inference: station-blocked bootstrap, 2,000 iterations, seed `20260713`,
  95% percentile confidence interval. Stations, not rows, are resampled.
- Label rule: score only rows with `measured_et_mm` present, which is non-gap
  `ET_corr` from the flux dataset. The raw-ET column is never a label.
- Stratification: Croplands versus non-Croplands; report H2 within each group.
- B0 uses only the preceding day's labeled tower value within each test series;
  it is reported as an oracle-ish diagnostic floor and is not used for H2.

Results and the decision are emitted by `mlet evaluate` to
`docs/results/phase2_openet_value.md`. The negative branch is reported when the
pre-registered threshold is not met.
