# Tier 3 gridMET selector results

This run tunes Gain and evaluates two deferral baselines. It uses the frozen [Tier 3 protocol](../../evaluation/ML_TIER3_GRIDMET_PROTOCOL.md).

## Evaluation

The run tests nine rolling years from 2012 through 2020. It includes 7,842 rows from 101 stations and 64 proximity groups. It reuses the frozen ten-member outer predictions.

The search evaluates 108 Gain configurations per test year. It uses four feature sets and three spatial folds. The receipt records one 251.0-second run on macOS 26.6.2 arm64. It records no timing interval. The run uses NumPy 2.4.3, pandas 2.3.3, and scikit-learn 1.8.0.

The paired intervals use 2,000 group-bootstrap draws and seed 20260924.

All 270 inner neural members reach 120 iterations. All 270 members report a convergence warning. This may limit selector quality.

## Primary comparisons

One of 52 comparisons has a Holm-adjusted p-value below 0.05. Under the synthetic temperature-plus-32 C transform, TunedGain lowers station-macro MAE by 0.0659 mm/day versus Gain. The paired 95% group-bootstrap interval is 0.0317 to 0.1047 mm/day. The one-sided group sign-flip p-value is 0.00055. The Holm-adjusted p-value is 0.02860.

This result covers one synthetic input fault. It does not establish improvement on a natural sensor fault.

Under clean inputs, TunedGain has station-macro MAE of 0.8120 mm/day. Gain has 0.8058 mm/day. This comparison uses 7,842 rows, 101 stations, and 64 groups. The paired improvement estimate is -0.0062 mm/day, with a 95% interval from -0.0222 to 0.0070. The one-sided sign-flip p-value is 0.751. Tuning does not improve clean-input results.

Under the temperature-plus-32 C transform, Gain has MAE of 1.4757 mm/day. It accepts 7,176 of 7,842 rows. Its station-macro acceptance is 88.1%, with a 95% group-bootstrap interval from 84.7% to 91.3%. TunedGain has MAE of 1.4097 mm/day. It accepts 6,514 rows. Its station-macro acceptance is 79.9%, with an interval from 73.8% to 85.4%. This comparison uses 101 stations and 64 groups. SupportGain rejects all 7,842 rows and returns OpenET, with MAE of 0.8544 mm/day. TunedGain has 0.5553 mm/day higher MAE than SupportGain. Its paired improvement interval is -0.6889 to -0.4321 mm/day. The tuned selector reduces error versus Gain, but it does not match the support gate.

No Holm-adjusted comparison shows that LogisticSign or ConformalCSR improves on SupportGain. The conformal selector makes no temporal coverage claim. Repeated stations and temporal shift violate the required independence assumption.

## Reproduction

The prediction tables, selector choices, calibration records, comparisons, and receipts are in this directory. The receipts bind the cohort, code, protocol, predictions, and library versions.

The conformal baseline follows [Sokol et al., Conformalized Selective Regression](https://arxiv.org/abs/2402.16300). This evaluation uses group calibration and does not claim temporal coverage.

The [risk-coverage analysis](../ml_tier3_gridmet_risk_coverage/README.md) reports the full curves, AURC intervals, fixed gate coverage, and fallback error.
