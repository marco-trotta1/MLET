# Tier 1 spatial holdout audit

Status: exploratory. The method choices and archive outcomes were visible before this evaluation.

## Question

Measure Gain and SupportGain on spatial groups excluded from model fitting.
This tests transfer to held-out groups, not to an independent data source.
It does not test forecasting because training can use later dates from other groups.

## Data and split

Use the physically screened gridMET cohort with 16,366 rows, 151 stations, and 102 groups.
Assign groups with field_withheld_folds, five folds, and seed 20261006.
Use fold zero as the test set. Keep every row from each test group out of training.
Train on all dates from the remaining groups.
Use three inner group folds with seed 20261007 for selector fitting.
Keep the ten-member ensemble, neural seeds, features, and selectors from the existing Tier 1 gridMET pipeline.
Save all row identifiers, groups, stations, and split assignments.

## Primary outcomes

Compare Gain directly with SupportGain on these five conditions: clean, wind multiplied by 2.237, wind multiplied by 3.6, Fahrenheit read as Celsius, and VPD multiplied by ten.
Define the paired difference as Gain MAE minus SupportGain MAE.
Positive values favor SupportGain.
Use station-macro MAE and station-weighted acceptance.
Resample test spatial groups with replacement for 2,000 draws.
Use seed 20261060 and the same resampled groups for all conditions.
Report marginal percentile intervals and simultaneous 95% bootstrap intervals across the five conditions.
Do not calculate p-values.

Intervals condition on the fitted models and one selected spatial split.
Treat all comparisons as exploratory, not as independent confirmation.
Report every estimate, including negative results.

## Reproduction

Run python3 scripts/run_ml_tier1_spatial_holdout.py from the repository root.
The script refuses to overwrite an existing result directory.
It saves predictions, split assignments, fit records, analysis results, and figures.
