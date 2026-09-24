# Tier 3 gridMET selector protocol

Status: fixed before selector fitting. This run uses the frozen ten-member
Tier 1 cohort and outer predictions.

## Data and outer evaluation

Use the cohort and nine rolling test years from
`ML_TIER1_GRIDMET_10MEMBER_PROTOCOL.md`. Reuse its saved outer neural
predictions. Regenerate the inner out-of-fold predictions with its ten seeds.
Use inner predictions for selector fitting and tuning. Do not use outer labels
for selector choices.

Evaluate the clean condition and all twelve fixed weather transforms. Keep
station-macro MAE as the selector objective. Report pooled MAE, RMSE,
station-macro acceptance, and paired group-bootstrap intervals.

## Tuned Gain selector

Use the current six features as the base: correction, absolute correction,
ensemble spread, log(1 + support distance), OpenET, and ETo. The base already
contains log(1 + support distance). Add raw temperature, VPD, and wind as one
feature set. Add day-of-year sine and cosine as another. Add both sets as a
fourth option.

Search every feature set with all 27 combinations below:

- Iterations: 40, 80, or 120.
- Leaf nodes: 3, 7, or 15.
- Learning rate: 0.03, 0.05, or 0.10.

Keep minimum leaf size 50, L2 penalty 10, and the fixed audit seed. Use the
three inner spatial folds for grouped cross-validation. Train on two folds.
Validate on the third. Choose the combination with the lowest mean
station-macro MAE across folds. Break ties by fewer iterations, fewer leaf
nodes, lower learning rate, then simpler features. Refit that selector on all
inner predictions. Accept when predicted gain is above zero.

## Standard deferral baselines

Fit a station-weighted logistic sign classifier on the full enriched feature
set. Predict whether realized gain is positive. Use standard scaling,
balanced class weights, C equal to 1, and seed 20260713. Accept when its
positive-class probability is at least 0.5.

Fit a conformalized quantile regression baseline on the full enriched feature
set. Predict the 2.5th and 97.5th percentiles of the neural residual error
with histogram gradient boosting. Use 80 iterations, 7 leaf nodes, learning
rate 0.05, minimum leaf size 50, and L2 penalty 10.

Split the inner spatial groups into fit, calibration, and threshold sets.
Shuffle groups with seed 20260924 plus the test year. Give the sets equal
numbers of groups. Train quantile models on the fit set. For each calibration
group, retain its largest CQR nonconformity score. Set the conformal offset
to the sorted score at rank ceil((G + 1) * 0.95), where G is the calibration
group count. Set the offset to infinity if this rank exceeds G.

Set the deferral score to max(upper bound - lower bound, 0). Choose its
threshold on the threshold set by minimum station-macro MAE. Break ties by
higher acceptance. Apply that fixed threshold to each outer test condition.
Conformal coverage is not claimed under temporal shift or repeated stations.

## Primary comparisons

Use one-sided paired group sign-flip tests. Positive change means lower MAE
for the first method. Apply Holm correction across all 52 tests below.

- TunedGain versus Gain across all thirteen conditions.
- TunedGain versus SupportGain across all thirteen conditions.
- LogisticSign versus SupportGain across all thirteen conditions.
- ConformalCSR versus SupportGain across all thirteen conditions.

Use 20,000 sign-flip draws and 2,000 group-bootstrap draws. Set both seed
bases to 20260924. Treat every other comparison as exploratory.

## Reproducibility

Write results to `docs/results/ml_tier3_gridmet/`. Save every prediction,
selected feature set, tuning score, split assignment, calibration offset,
threshold, fit warning, timing, code hash, data hash, and library version.
Do not overwrite prior results.
