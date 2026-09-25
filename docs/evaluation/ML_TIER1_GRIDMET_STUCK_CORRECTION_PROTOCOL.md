# Tier 1 GridMET stuck-wind correction

Status: exploratory correction. The earlier outcomes were inspected.

## Reason

The earlier transform operated on sparse evaluation rows. It changed wind for
137 of 7,842 test rows. It did not model a seven-day hold on daily weather.
Keep the earlier results for audit. Do not interpret that condition as a
seven-day stuck input.

## Transform

Use each station-year's daily GridMET wind series from the saved NetCDF cache.
Start seven-day blocks at the first date in each station-year file. For each
evaluation row, use the wind value from the first day of its block. This
definition uses no future value or target label. It models a synthetic input
fault. It does not represent an observed sensor failure.

Apply this transform to inner augmentation rows and outer evaluation rows.
Keep the cohort, years, splits, models, methods, and other transforms fixed.
Keep the original outputs unchanged. Save the corrected run in
`docs/results/ml_tier1_gridmet_stuck_corrected/`.

## Exploratory summaries

Report complete-system station-macro MAE and station-weighted acceptance.
Report these paired contrasts: SupportGain versus Gain on stuck-wind rows,
MonoGain versus SupportGain on stuck-wind rows, AugmentedGain versus
SupportGain on stuck-wind rows, and AugmentedGain versus SupportGain on clean
rows.

Use 2,000 paired group-bootstrap draws with seed 20260925. Do not report
one-sided tests or Holm-adjusted values. These results are exploratory because
the original outcomes were visible before this correction.

## Records

Save the corrected daily wind input for every cohort row. Save source hashes,
run hashes, versions, timings, warnings, predictions, and analysis output.
