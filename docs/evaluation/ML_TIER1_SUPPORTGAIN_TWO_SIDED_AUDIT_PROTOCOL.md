# Tier 1 SupportGain two-sided audit

Status: exploratory reanalysis after outcome review.
The saved outcomes were visible before this protocol.

## Question

Check whether the SupportGain versus Gain, MonoGain, and AugmentedGain results
remain after allowing either method to have lower error.
Use the same 13 conditions and saved ten-member predictions as the directional
audit.

## Comparisons

Compare station-macro MAE for SupportGain with each baseline in every
condition. A positive difference favors SupportGain. Keep the 39 comparisons
in one family. Keep fitted models, thresholds, rows, and labels fixed.

## Inference

Use paired spatial-group bootstrap intervals with 2,000 draws and seed
20260925 plus the comparison index. Use a two-sided spatial-group sign-flip
test with 20,000 draws and the same seed rule. Apply Holm correction once to
all 39 two-sided p-values. Report the signed difference, interval, original
one-sided p-value, two-sided p-value, and adjusted two-sided p-value.

This check allows either direction within each comparison. Earlier outcome
review and method selection remain. The results are exploratory and do not
provide independent confirmation.

## Reproducibility

Use the saved predictions from the fixed ten-member run. Verify their hashes
against the directional audit receipt. Save the protocol, code, source,
result, and receipt hashes. Do not overwrite completed two-sided results.
