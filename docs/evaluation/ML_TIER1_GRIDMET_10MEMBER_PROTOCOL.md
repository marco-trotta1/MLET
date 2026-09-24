# Tier 1 all-station temporal protocol: ten-member ensemble

Status: fixed before the ten-member model run. The three-member run remains
preliminary.

Apply `ML_TIER1_GRIDMET_PROTOCOL.md` in full. Keep its cohort, splits, test
years, selector settings, fault transforms, metrics, bootstrap, and primary
comparison family.

## Neural ensemble

Fit ten neural members for each inner and outer training set. Use seeds
20260713 through 20260722. Keep the network architecture, optimizer, feature
scaling, target scaling, iteration limit, and all other settings from
`scripts/ml_selective_residual.py`.

Calculate ensemble spread from the ten member predictions with the sample
standard deviation. Recompute correction, spread, and support distance for
each transformed input used by augmented selector training.

Save this run under `docs/results/ml_tier1_gridmet_10member/`. Keep the
three-member results under `docs/results/ml_tier1_gridmet/`. Do not combine
their predictions or metrics.
