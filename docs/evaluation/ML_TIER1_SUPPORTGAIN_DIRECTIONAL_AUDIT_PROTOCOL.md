# Tier 1 SupportGain directional audit

Status: exploratory reanalysis of saved ten-member predictions.
The original results were visible before this audit.

## Question

Measure whether SupportGain has lower station-macro MAE than Gain,
MonoGain, and AugmentedGain under the fixed clean and transformed inputs.
This audit does not refit models or change the original primary tests.

## Inputs and comparisons

Use the saved 7,842-row predictions from the ten-member Tier 1 run.
Keep its 101 stations, 64 groups, fitted models, and selector thresholds.
Use the 13 conditions in the original primary family.

Compare SupportGain with Gain, MonoGain, and AugmentedGain in every condition.
This gives one family of 39 paired comparisons.
Define a positive difference as lower MAE for SupportGain.
Do not add subgroups or select conditions after inspecting results.

## Metrics and inference

Report station-macro MAE differences and paired 95% spatial-group bootstrap
intervals. Use 2,000 draws with seed 20260925.
Use the existing one-sided spatial-group sign-flip procedure.
Use 20,000 draws, with seed 20260925 plus the comparison index.
Apply Holm correction once across all 39 comparisons.
Report every point estimate, interval, raw p-value, and adjusted p-value.

These tests are exploratory. They use the same saved outcomes that motivated
the reverse-direction question. They cannot provide independent confirmation.
Do not replace, reinterpret, or combine them with the original 40-test family.

## Reproducibility

Save the source prediction hashes, protocol hash, code hash, seeds, versions,
all comparison rows, and analysis receipt.
Refuse to overwrite completed results.
