# Tier 3 risk-coverage protocol

Status: fixed before risk-coverage analysis. Treat all results as descriptive.

## Data and methods

Use the frozen Tier 3 outer predictions for nine test years from 2012 through
2020. The clean condition has 7,842 rows, 101 stations, and 64 proximity
groups. Analyze the clean condition and all twelve fixed weather transforms.

Evaluate Gain, SupportGain, MonoGain, AugmentedGain, TunedGain, LogisticSign,
and ConformalCSR. Do not fit a new outer model. Use the saved prediction scores
and selector receipts.

Use these confidence scores. Higher scores mean higher confidence.

- Gain: `predicted_gain`.
- MonoGain: `predicted_monotone_gain`.
- AugmentedGain: `predicted_augmented_gain`.
- TunedGain: `tuned_predicted_gain`.
- LogisticSign: `logistic_sign_probability`.
- ConformalCSR: `1 - conformal_width / threshold`, with the saved threshold
  for each test year.
- SupportGain: the minimum of two dimensionless margins. Divide
  `predicted_gain` by the weighted interquartile range of its inner selector
  scores. Divide `inner 95th-percentile support distance - support_distance`
  by the weighted interquartile range of inner support distances. Take the
  smaller value. Rebuild inner out-of-fold predictions from the saved splits
  to get both ranges and the support threshold. Use station weights. Verify
  that a positive joint score matches the saved SupportGain gate, except for
  rows at an exact zero margin. Use the saved gate for its fixed operating
  point.

The fixed operating point uses each saved acceptance flag. Gain, MonoGain,
AugmentedGain, and TunedGain use a zero score threshold. LogisticSign uses a
probability threshold of 0.5. ConformalCSR uses its saved width threshold.

## Risk and coverage

Use equal station weights. Set each row weight to the inverse of that
station's row count. Coverage is the weighted fraction of accepted rows.
Selective risk is the weighted mean absolute error of `OpenET + correction`
among accepted rows. A rejected row has no selective risk value.

Compute each curve at station-weighted coverage levels 0.01 through 1.00.
Accept a fractional share of the boundary score group to match each budget.
Group scores into ties with an absolute tolerance of 1e-12 in score units.
Compute AURC as the mean of the 100 risk values. Report AURC in mm/day.

Also report each saved gate's fixed operating point and its end-to-end
station-macro MAE. End-to-end predictions use the saved fallback to OpenET.
Do not confuse end-to-end MAE with selective risk.

## Uncertainty and reporting

Resample the 64 proximity groups with replacement. Keep all station rows in
each sampled group. Keep model scores and fits fixed. Recompute the risk curve
for each of 2,000 bootstrap draws. Use RNG seed 20261004 plus the condition's
zero-based index in `ML_TIER1_GRIDMET_10MEMBER_PROTOCOL.md`.

Report percentile 95% intervals for every curve point and AURC. These
intervals condition on the fitted models and scores. They do not include
retraining or selector threshold uncertainty. Do not report p-values or claim
that one method is superior from these intervals. The thirteen conditions and
seven methods share data.

Use the clean and temperature-plus-32 C curves in Figure 17. Save curves and
AURC for all thirteen conditions. Write results to
`docs/results/ml_tier3_gridmet_risk_coverage/`. Follow the figure palette and
layout in `figures4papers`. Save PDF and 300 dpi PNG output.
