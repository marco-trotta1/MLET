# Selective neural residual correction

Status: exploratory extension fixed before this experiment runs.
The previous MLET results and humidity anomaly are already known.
This protocol does not create an untouched confirmation dataset.

## Question

Can a selector distinguish helpful neural corrections from harmful corrections at unseen spatial groups?
Does ranking uncertainty give the same decision as ranking improvement over the available satellite estimate?

## Fixed data and partitions

Use the existing 7,923-row cohort and saved proximity and joint partitions.
The joint partitions train before 2019 and test in 2019 through 2020.
Use all saved inner partitions, including the earlier-to-later inner restriction for joint evaluation.
No outer labels enter scaling, neural fitting, selector fitting, or threshold selection.
Run both archived inputs and the six-input specification without VPD.
Keep all natural-test targets, including the previously identified humidity anomalies.

## Neural estimator

Use the existing residual MLP: two 32-unit ReLU layers, Adam, and 120 epochs.
Use learning rate 0.001, batch size 256, L2 parameter 0.001, and no early stopping.
Standardize inputs and residual targets using each training partition only.
Use seeds 20260713, 20260714, and 20260715.
Average predictions across seeds. Record their sample standard deviation with ddof=1.
Compare each refitted outer prediction with the corresponding saved prediction.
Retain convergence warnings and every seed prediction.

## Selectors and controls

All selectors use the same outer neural predictions.
The default prediction is unchanged OpenET.
An accepted correction adds the ensemble mean residual to OpenET.

- Full: accept all corrections.
- Spread95: accept below the station-weighted 95th percentile of inner ensemble spread.
- Support95: accept below the station-weighted 95th percentile of inner support distance.
- Gain: accept if a fitted selector predicts positive absolute-error improvement.
- SupportGain: require both Support95 and Gain acceptance.
- Uniform: choose a single multiplier from 0, 0.25, 0.5, 0.75, and 1 using inner station MAE.
- Clip: clip available weather inputs to outer-training first and 99th percentiles before neural inference.
- OpenET: apply no learned correction.

Support distance is the mean distance to five nearest training inputs in standardized input coordinates.
Fit the scaler and neighbor index separately within every inner partition and outer training partition.
The distance threshold comes from inner held-out predictions, never training self-distances.
This is a simple applicability-domain control, not an implementation of GeoQ or the published weighted AOA method.

The gain target is |y - OpenET| - |y - OpenET - correction|.
The selector uses six features: signed correction, absolute correction, ensemble spread, log(1 + support distance), OpenET, and ETo.
Use histogram gradient boosting with 80 iterations, learning rate 0.05, seven leaves, minimum leaf size 50, and L2 parameter 10.
Disable early stopping. Set the seed to 20260713.
Use station weights normalized to mean one.
Construct every selector target from inner out-of-group neural predictions.
The selector is a fixed comparison method, not a claimed new architecture.

## Outcomes

The primary outcome is station-macro MAE on every outer test row, including fallback predictions.
Report pooled MAE, RMSE, acceptance fraction, and station-macro acceptance.
Report cropland results separately.
Use 2,000 paired proximity-component bootstrap samples with seed 20260922.
Intervals condition on the fitted models and do not correct for multiple exploratory comparisons.
Report all methods in both input specifications and both evaluation regimes.

For spread, support distance, and predicted gain, save curves at inner acceptance quantiles 0, 0.1, ..., 1.
Keep the endpoints exactly all-fallback and all-correction.
Report realized outer acceptance, full-population MAE, and accepted-subset neural and baseline MAE.
The outer acceptance fraction need not match the inner requested fraction under distribution shift.
Report AUC for detecting harmful corrections where both outcome classes exist.

## Controlled input faults

After all fitting and selection, apply three separate test-only faults: VPD multiplied by 10, wind multiplied by 10, and temperature increased by 20 degrees Celsius.
Use only test rows whose exported actual vapor pressure is nonnegative for these probes.
Keep their labels, baseline estimates, fold assignments, and all fitted parameters fixed.
Apply each fault separately to every eligible row. These probes do not estimate fault prevalence.
VPD corruption has no effect in the no-VPD arm and serves as an exact negative control.
Save full paired predictions. Compare each fault with its identical unmodified probe rows.
Fault results measure robustness to input corruption, not real weather interventions or independent external validation.

## Records and stopping

Save inner predictions, outer predictions, selectors, thresholds, fit times, warnings, and every seed result.
Record source and protocol hashes, cohort hash, package versions, platform, and seed values.
Run this fixed experiment once. Do not adjust a model after viewing its outer outcomes.
Retain negative results and failed selectors.
