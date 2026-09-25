# Tier 1 measured-weather implementation correction

Status: fixed before the correction run. This run is exploratory because the
original outcomes were inspected.

## Reason

The original measured-weather run recomputed the correction for each
augmented input. It reused clean-input ensemble spread and support distance.
The frozen protocol requires all three outputs to come from the transformed
input. This correction follows that rule. It does not add a method or change
the fault transforms.

Keep the original run and its outputs unchanged. Save the corrected run in
`docs/results/ml_tier1_selective_corrected/`.

## Fixed run

Use the same clean cohort, proximity splits, three-member ensemble, model
settings, fault transforms, and seeds as the original measured-weather run.
For every transformed inner-validation input, recompute the residual
correction, ensemble spread, and five-neighbor support distance. Build the
augmented selector features from those outputs and the transformed input.
Compute the training target from the recomputed correction.

Keep all other code paths fixed. Fit all ten proximity folds once. Save full
predictions, acceptance, hashes, versions, warnings, fit time, and negative
results. Do not overwrite the original run.

## Named comparisons

Use these eleven comparisons. Define positive change as lower station-macro
MAE for the first method.

- LocalShrinkage versus SupportGain on clean rows.
- LocalShrinkage versus Uniform on clean rows.
- SupportGain versus Gain under wind multipliers 3.6, 5, and 10.
- SupportGain versus Gain under Fahrenheit-as-Celsius and VPD multiplied by
  ten.
- AugmentedGain versus SupportGain under wind multipliers 5 and 10,
  Fahrenheit-as-Celsius, and VPD multiplied by ten.

Use 2,000 paired group-bootstrap draws with seed 20260922. Use 20,000
one-sided group sign-flip draws. Apply Holm correction across all eleven
comparisons. Report every result as exploratory. Do not claim independent
confirmation from this corrected run.

## Visuals

Build the dose-response, fault-type, and mechanism figures with the existing
figures4papers workflow. Save corrected figures under
`manuscript/arxiv/figures/tier1_selective_corrected/`.
