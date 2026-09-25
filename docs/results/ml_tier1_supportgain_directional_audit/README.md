# Tier 1 SupportGain directional audit

This audit compares SupportGain with three selectors on the saved ten-member predictions.
It uses 7,842 rows from 101 stations and 64 spatial groups.

The comparison direction was selected after the outcomes were visible.
Treat these results as exploratory evidence and not as independent confirmation.
The 39 tests use one Holm family, but that adjustment does not remove the earlier direction choice.

The original directional audit uses one-sided tests after selecting SupportGain's direction from visible outcomes.
After its one-sided Holm adjustment, SupportGain has lower station-macro MAE than Gain in 11 of 13 conditions.
It has lower MAE than MonoGain in nine of 13 conditions.
It has lower MAE than AugmentedGain on clean input.
The later two-sided audit allows either method to win within each comparison.
After two-sided Holm adjustment, 19 of 39 comparisons remain below 0.05: 10 against Gain, nine against MonoGain, and none against AugmentedGain.

For clean SupportGain versus AugmentedGain, the difference is 0.0416 mm/day.
Its two-sided Holm-adjusted p-value is 0.051.
The clean SupportGain versus Gain difference is 0.0052 mm/day, with a 95% group interval from -0.0041 to 0.0149.
The clean SupportGain versus AugmentedGain difference is 0.0416 mm/day, with a 95% group interval from 0.0158 to 0.0699.
Its two-sided Holm-adjusted p-value is 0.051.

For VPD multiplied by ten, SupportGain reduces station-macro MAE by 2.8541 mm/day versus Gain.
The 95% group interval is 2.2508 to 3.5391 mm/day.
The two-sided sign-flip p-value is 0.00005, and the two-sided Holm-adjusted p-value is 0.00195.
This transformation simulates a kPa-to-hPa error.
It does not estimate the frequency of real sensor faults.

The primary 40-comparison result remains unchanged.
No comparison in that prespecified direction family passes Holm correction.
The audit uses the same saved model outputs and cannot establish independent replication.

The one-sided protocol is in ML_TIER1_SUPPORTGAIN_DIRECTIONAL_AUDIT_PROTOCOL.md.
The two-sided protocol is in ML_TIER1_SUPPORTGAIN_TWO_SIDED_AUDIT_PROTOCOL.md.
The tables are in comparisons.json and two_sided_comparisons.json.
The receipts record input hashes, code and protocol hashes, seeds, and package versions.
Both audit scripts refuse to overwrite completed results.
