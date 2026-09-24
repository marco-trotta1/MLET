# Tier 1 all-station temporal protocol

Status: fixed before the all-station model run. This is a new input arm. It
does not replace the measured-weather experiment or its saved results.

## Question

Test whether the selective correction results persist across nine annual test
sets when gridMET supplies weather for all benchmark stations. Train only on
years before each test year. This tests temporal transfer. It does not test
transfer to unseen stations.

## Cohort

Start from the exact station-date join in `data/interim/all_stations.csv`.
Join daily gridMET wind, minimum and maximum temperature, and VPD by station
coordinates and date. Keep rows with finite measured ET, OpenET, ETo, and
gridMET weather. Require wind from 0 through 75 m/s, minimum and maximum
temperature from -50 through 60 C, and VPD from zero through saturation vapor
pressure at the daily maximum temperature. Use
`es(T) = 0.6108 exp(17.27 T / (T + 237.3))` kPa for this final check.

Exclude a row when an available station-measured weather value fails the
physical screen in `ML_TIER1_SELECTIVE_PROTOCOL.md`. Missing station weather
does not exclude a gridMET row. Report missing and rejected counts separately.
Use station-measured weather only for the complete, physically valid
sensitivity arm.

Set `t_avg` to the mean of gridMET minimum and maximum temperature. Use native
gridMET VPD and 10 m wind. Use the fixed features `openet`, `eto`, day-of-year
sine and cosine, `t_avg`, `vpd`, and `ws`.

## Evaluation

For each test year from 2012 through 2020, train on all earlier years and test
on that year. A station can occur in both periods. Assign spatial groups with
a 10 km proximity threshold and seed 20260924. Use three shuffled group folds
for selector cross-fitting inside each training period. Fit the outer neural
ensemble on all rows before the test year. Do not use test labels for fitting.

Keep the fixed three-member network, feature scaling, selector settings, and
fault transforms from `scripts/ml_tier1_selective.py`. Apply the dose-response
and sensor-fault transforms to test inputs only. Do not add noise because the
source archive gives no sensor-accuracy specification.

Report station-macro MAE, pooled MAE, RMSE, and acceptance for every method,
condition, and test year. Also report pooled results across all nine years.
Report paired 95% intervals from 2,000 group-bootstrap draws with seed
20260924. Keep all predictions and fit warnings.

## Primary comparisons

Use one-sided paired group sign-flip tests. Apply Holm correction across the
complete family below. Define positive change as lower MAE for the first
method.

- Gain versus SupportGain for clean, every wind dose, every temperature dose,
  Fahrenheit-as-Celsius, and VPD x10.
- MonoGain versus SupportGain for the same conditions.
- AugmentedGain versus SupportGain for the same conditions.
- LocalShrinkage versus Uniform on clean rows.

Treat other comparisons as exploratory. Report negative and inconclusive
results. Do not claim that a weather fault represents a real sensor failure.

## Reproducibility

Do not overwrite prior results. Save the protocol hash, code hash, input
hashes, station-year coverage, split assignments, seeds, versions, timings,
warnings, complete predictions, and correction results before analysis.
