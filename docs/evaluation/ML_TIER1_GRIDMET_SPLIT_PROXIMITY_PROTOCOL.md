# Tier 1 gridMET split and proximity sensitivity protocol

Status: fixed before these sensitivity runs. Treat every result as secondary to
the frozen Tier 1 temporal comparison.

## Question

Measure how the pooled Gain versus SupportGain error gap changes across inner
fold seeds and proximity thresholds. This sensitivity does not test transfer
to unseen stations. The outer evaluation remains temporal, and stations may
appear in both periods.

## Data and model

Use the fixed 16,366-row gridMET cohort from
`docs/results/ml_tier1_gridmet/cohort.csv`. Keep every row and feature. Assign
proximity groups from the station metadata coordinates with thresholds of 5,
10, and 25 km. Use the same Haversine distance and connected-component rule as
the cohort builder. These thresholds produce 113, 102, and 86 groups.

For each threshold, evaluate ten split seeds: 20260924 through 20261003.
For each rolling test year from 2012 through 2020, assign three inner spatial
folds with `split_seed + test_year`. Keep the ten neural seeds, model settings,
fault transforms, and all other Tier 1 code fixed.

Rerun the full Tier 1 pipeline for every threshold and seed. Reuse the frozen
10 km, seed 20260924 run after its cohort, split, script, and neural-seed
hashes match. This arm is an anchor, not a new replicate. Run every other
threshold and seed as a new fit.

## Outcomes and analysis

The primary outcome is the clean pooled station-macro MAE gap:
`Gain MAE - SupportGain MAE`. A positive value means SupportGain has lower
error. Report this value for every threshold and seed. Also report its mean,
sample standard deviation, minimum, maximum, and count of positive values over
the ten seeds at each threshold.

Report the same summaries for all twelve fixed weather transforms as
sensitivity results. For every run and condition, report a paired 95%
group-bootstrap interval from 2,000 draws. Set its seed to
`20260924 + 100 * threshold_km + seed_index`, where seed_index is zero through
nine in the listed seed order.

Treat seed variation as a stability summary. Do not use a p-value across
seeds. The runs share data and are not independent samples. Do not claim
spatial transfer from inner-fold assignments.

## Reproducibility

Write results to `docs/results/ml_tier1_gridmet_sensitivity/`. Save each run's
protocol hash, code hash, cohort hash, split assignments, library versions,
runtime, fit warnings, and method metrics. Keep all thirteen condition
summaries and preserve compressed Gain and SupportGain predictions with row,
year, station, group, and target fields.

Do not overwrite the frozen Tier 1 or Tier 3 results. Keep the original
ten-member run as the 10 km, seed 20260924 anchor.
