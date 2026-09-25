# Study limitations

The cropland comparison was fixed before its fit. SupportGain was selected from earlier test outcomes on the same archive.
Those outcomes include the cropland test rows. The paired interval does not account for that method choice or model retraining.
No independent archive confirms the improvement.

The gridMET screen retains 16,366 rows from 151 stations. Rolling tests use 7,842 rows from 101 stations.
The cropland comparison uses 3,234 test rows from 49 stations and 24 proximity groups.
Stations recur across test years. The study tests temporal transfer, not transfer to unseen stations.
The complete-weather screen can favor stations with available inputs.

The land-cover label does not identify irrigated fields. The data do not provide reliable irrigation-action labels.
The target is corrected actual ET from retrospective flux observations. The study does not estimate irrigation effects, water savings, or forecast skill.
Upstream OpenET development may overlap the validation archive.

The primary predictor uses a fixed ten-member ensemble. All 360 cropland neural fits reach the 120-iteration limit and report convergence warnings.
The study does not establish superiority over all selector or deferral methods.
Crop-only Full has lower point MAE than crop-only SupportGain on the primary test rows.

Synthetic input faults preserve labels and the satellite fallback. They do not estimate natural fault prevalence or physical weather-change effects.
The known natural archive fault has 32 rows from one held-out station. It cannot support a population uncertainty interval.
The exploratory extension excludes that station. It has 133 invalid rows from 21 stations and 17 groups.
Only two groups show a nonzero Gain versus SupportGain difference. Its paired interval touches zero.
Unchanged OpenET has lower point error than both selectors on those rows.
The archive was inspected before the extension protocol, so this is not independent confirmation.
A physical rule violation does not establish a sensor failure.
The primary weather inputs are gridMET estimates, so no single device accuracy applies to them.
The station metadata workbook lists measurement technique but no instrument model or rated accuracy.
The variable workbook lists units and definitions, not instrument specifications.
The measured-weather arm therefore has no source-based scale for an additive-noise experiment.

The paired bootstrap keeps fitted models and selectors fixed. It assumes proximity groups are independent resampling units.
The adjusted selector comparisons have a separate 52-test family. The crop-only analysis names one primary contrast and treats other comparisons as descriptive.
