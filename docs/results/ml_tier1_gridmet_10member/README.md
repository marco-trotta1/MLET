# Tier 1 all-station temporal results

Status: one fixed ten-member run. The three-member run remains preliminary.

The protocol was committed before fitting. Commit: `25c5090`. Its SHA-256
hash is `f825d4eda6e719b39cd1d42af89edae3f7b09e06efc9ee1ca5e763e5cee03d9a`.

## Cohort and split

The input joins 16,447 labeled station-days from 152 stations. The physical
screen retains 16,366 rows from 151 stations and 102 proximity groups. It
removes 24 rows for temperature, 8 for gridMET VPD, 54 rows with invalid
weather values from the station archive, and 3 for missing measured ET. Rule
counts overlap. The audit field `sensor_fault` marks these physical rule
violations. It does not confirm a faulty instrument.

The rolling-origin tests cover 2012 through 2020. They contain 7,842 rows
from 101 stations and 64 spatial groups. Each year trains only on earlier
years. Stations can occur in both periods, so this is temporal transfer.

## Main results

The primary family has 40 planned comparisons. None has a Holm-adjusted
one-sided p-value below 0.05. The smallest adjusted value is 0.126 for
AugmentedGain versus SupportGain under a 20 C temperature shift.
The one-sided tests ask whether each first-listed method improves on its
baseline. The Gain, MonoGain, and AugmentedGain tests therefore do not test
whether SupportGain improves on those methods. Treat support-favoring results
below as descriptive.

On clean test rows, SupportGain has station-macro MAE 0.801 mm/day. OpenET
has 0.854 mm/day. The paired improvement is 0.054 mm/day, with a 95% group
bootstrap interval from 0.014 to 0.101 across 64 groups. This comparison is
descriptive. It is outside the corrected primary family.

On clean rows, LocalShrinkage does not improve on Uniform. Its paired MAE
change is -0.003 mm/day, with a 95% interval from -0.018 to 0.010 across 64
groups. Its one-sided p-value is 0.669.

Under wind x10, Gain has station-macro MAE 1.474 mm/day and accepts 86.8% of
rows. SupportGain has MAE 0.855 mm/day and accepts 0.13%. This is a synthetic
input transformation. It does not establish real sensor-fault performance.
The weather response figure shows saved station-macro MAE reductions and
acceptance rates for the fixed probe conditions. Its VPD panel shows one
kPa-to-hPa error, not a dose curve.

The run performs 360 ensemble fits. Every fit reaches the 120-iteration
limit and records a convergence warning. Treat this limit as a study
limitation.

## Stuck-wind audit

The original seven-day stuck-wind transform changed only 137 of 7,842 test
inputs because it operated on sparse evaluation dates. Do not interpret that
condition as a daily seven-day hold. The [corrected exploratory report](../ml_tier1_gridmet_stuck_corrected/README.md)
uses the saved daily GridMET series and preserves this run for audit.

## Files

- [Primary comparisons](primary_comparisons.json)
- [Run receipt](receipt.json)
- [Analysis receipt](analysis_receipt.json)
- [Rolling-origin figure](../../../manuscript/arxiv/figures/figure_14_tier1_gridmet_10member_rolling_origin.png)
- [Wind dose figure](../../../manuscript/arxiv/figures/figure_15_tier1_gridmet_10member_wind_dose.png)
- [All weather-fault responses](../../../manuscript/arxiv/figures/figure_20_tier1_gridmet_10member_weather_fault_response.png)
- [Ten-member protocol](../../evaluation/ML_TIER1_GRIDMET_10MEMBER_PROTOCOL.md)
- [Cohort receipt](../ml_tier1_gridmet/cohort_receipt.json)

Every condition has saved predictions. The run receipt records seeds,
versions, fit timings, split sizes, and warnings. The analysis uses 2,000
group-bootstrap draws and 20,000 sign-flip draws with seed 20260924.

The figures follow the typography, palette, axis, and vector-export guidance
in the [figures4papers repository](https://github.com/ChenLiu-1996/figures4papers).
