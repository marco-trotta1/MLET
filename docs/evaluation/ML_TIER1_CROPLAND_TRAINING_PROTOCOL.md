# Tier 1 cropland training protocol

Status: fixed before the cropland-only fit. Treat the result as a separate target-population analysis.

## Question and selected method

Test whether cropland-only training changes SupportGain accuracy on cropland test rows. The comparison uses the saved all-station SupportGain predictions as its baseline.

Select SupportGain before this analysis. It has the lowest fixed end-to-end station-macro MAE among seven Tier 3 selectors on clean all-station rows: 0.80066 mm/day. Keep its selector rule fixed.

The land-cover label does not identify irrigation. Do not describe this cohort as irrigated cropland.

## Population and splits

Use the fixed 16,366-row gridMET cohort in `docs/results/ml_tier1_gridmet/cohort.csv`. It has 5,203 Croplands rows from 58 stations and 30 proximity groups.

Select rows whose `landcover` value is `Croplands`. Keep the saved 2012 through 2020 rolling test years and inner spatial assignments. Intersect each fit, validation, and test partition with this fixed land-cover label. Do not move rows between partitions.

The pooled test set contains 3,234 rows from 49 stations and 24 groups. A station can occur in both training and test years. This tests temporal transfer within the cropland population. It does not test transfer to unseen stations.

Use only clean gridMET inputs. Do not apply weather faults.

## Model and selector

Fit each outer neural ensemble on Croplands rows from years before its test year. Use the ten seeds, architecture, feature scaling, target scaling, optimizer, and 120-iteration limit from `ML_TIER1_GRIDMET_10MEMBER_PROTOCOL.md`.

For each year, fit the inner neural ensembles on cropland-only fit rows. Predict only cropland validation rows. Build the same relative-benefit targets and selector features as Tier 1.

Fit the fixed Tier 1 Gain regressor on inner predictions. Use equal station weights, normalized to mean one. Set the support threshold to the station-weighted inner 95th percentile of five-neighbor distance. Accept a correction only when predicted gain is positive and distance is at or below that threshold. Return OpenET for every rejected row.

Do not tune model or selector settings. Do not use outer test labels for fitting or threshold selection.

## Outcomes and uncertainty

The primary outcome is the paired station-macro MAE difference on identical cropland test rows:

`all-station SupportGain MAE - cropland-only SupportGain MAE`.

A positive value favors cropland-only training. Report its point estimate and percentile 95% interval from 2,000 paired bootstrap draws over the 24 test groups. Keep each group's rows together. Set the bootstrap seed to 20261005. The interval conditions on fitted models and selectors.

Report station-macro MAE for OpenET, Full, and SupportGain for each training arm. Report SupportGain's station-weighted acceptance. Report pooled values by test year and for all test years. Label every comparison except the primary contrast as descriptive. Report no p-values.

## Reproducibility

Reuse saved all-station SupportGain predictions. Fit only the cropland-only arm. Verify exact equality of test row identifiers before comparing predictions.

Write run records to `docs/results/ml_tier1_cropland/`. Save predictions, split sizes, inner score scales, support thresholds, model warnings, runtime, software versions, and hashes for the protocol, source data, splits, and code.

Commit this protocol before the fit. Do not overwrite prior results.
