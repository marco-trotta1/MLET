# Tier 1 five-fold spatial holdout sensitivity

Status: post hoc. Fold zero was inspected before this extension.
Treat the pooled results as exploratory, not as independent confirmation.

## Analysis

Use the same five spatial folds, cohort, conditions, methods, and seeds as the original spatial holdout audit.
Reuse the saved fold-zero predictions after checking their split and code hashes.
Fit folds one through four with all rows from each test group held out.
Pool each row's single outer-fold prediction.
Require every test row to appear once, with no station overlap inside its fold.

Report the same direct Gain and SupportGain differences, station-weighted acceptance, and group bootstrap intervals.
Use simultaneous 95% intervals across the same five conditions.
Do not calculate p-values.
Intervals condition on the fitted models and do not include retraining uncertainty.

## Reproduction

Run python3 scripts/run_ml_tier1_spatial_holdout_sensitivity.py from the repository root.
The script reuses the original fold-zero results and refuses to overwrite its output directory.
