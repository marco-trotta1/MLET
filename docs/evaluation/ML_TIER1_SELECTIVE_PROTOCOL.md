# Tier 1 clean selective experiment

Status: fixed before the Tier 1 model run. This protocol extends the earlier
selective study. The earlier predictions and results remain unchanged.

## Data rule

Use the public archive's measured daily weather. Keep a row only when actual
vapor pressure is present and nonnegative, VPD is present and within zero to
saturation vapor pressure, wind is present and within zero to 75 m/s, and mean
air temperature is present and within -50 to 60 degrees Celsius. The source
workbook gives kPa for vapor pressure and VPD, m/s for wind, and Celsius for
temperature. Do not repair a row that fails a rule.

Apply the rule to all rows and stations in the labeled archive. Report each
rule's failure count, missing values, retained rows, and retained stations.
Use the retained rows with complete model inputs for the clean selective
experiment. Retain the source row IDs and the original proximity groups.

## Evaluation

Use the saved proximity-group outer folds. Remove invalid rows before each
fit. Use the existing three-seed neural residual ensemble and inner group
predictions. Keep the satellite estimate as the fallback. Do not use outer
labels for model or threshold selection.

Report station-macro MAE and station-macro acceptance for every selector. The
primary dose-response probes are wind multipliers 0, 0.447, 1, 2.237, 3.6, 5,
and 10; temperature offsets 0, 5, 10, 20, and 32 degrees Celsius plus a
Celsius-to-Fahrenheit conversion; and VPD multiplied by 10. Keep each fault
separate. Also report wind zero, wind dropout replaced by the training median,
seven-day stuck wind, and training-derived day-of-year wind climatology.

Compare Gain, SupportGain, a Gain model constrained to decrease with ensemble
spread and support distance, a Gain model trained on inner-fold fault
augmentations, global shrinkage, and local shrinkage. Gain already includes
log(1 + d5); do not count that existing feature as a new method. Estimate local
shrinkage from inner predictions with A = (y - OpenET)g and B = g squared,
then set lambda to clip(A estimate / B estimate, 0, 1). If B is nonpositive,
set lambda to zero.

Score the 32 invalid manilacotton rows as a separate natural-fault test. Use
only the outer fold that withholds their proximity group. Fit on valid rows.
Apply the corrupted source inputs only at test time. Do not use these rows to
fit the network or selector.

Use paired proximity-group bootstrap intervals with 2,000 draws and seed
20260922. Name the primary method comparisons in the result receipt before
the run. Treat every other comparison as exploratory. Save full predictions,
acceptance, data and code hashes, software versions, warnings, fit time, and
all negative outcomes. Run once. Do not overwrite existing experiment results.

## Scope

The first model run uses the measured-weather rows available in the current
benchmark. The source archive has 152 labeled stations, but measured weather
coverage is incomplete. GridMET weather inputs for all stations remain a
separate data expansion and are not part of this run.
