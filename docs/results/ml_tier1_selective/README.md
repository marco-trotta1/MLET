# Tier 1 clean-cohort result

Status: original measured-weather run, retained for audit. These results
condition on the fitted outer models.

## Correction notice

The original code reused clean-input ensemble spread and support distance for
fault-augmented rows. Its `AugmentedGain` results do not follow the protocol.
Use the [corrected exploratory run](../ml_tier1_selective_corrected/README.md)
for `AugmentedGain`. Keep these original files unchanged.

All other prediction columns match the corrected run in all 36 conditions.
The corrected `AugmentedGain` predictions differ in 18 conditions.

The cohort receipt recorded the protocol hash before model fitting. The
protocol was not committed before the run. The exact Holm comparison set was
assembled after the outcomes. Treat all adjusted p-values as exploratory.

## Physical screen

The audit covers 16,447 joined rows from 152 stations. It requires actual
vapor pressure at or above zero, VPD from zero through saturation vapor
pressure, wind from zero through 75 m/s, and mean air temperature from -50
through 60 degrees Celsius. The source workbook gives kPa, m/s, and Celsius.

The complete-weather cohort has 7,923 rows from 85 stations. The screen keeps
7,758 rows from 84 stations and 62 proximity groups. It rejects 50 rows with
negative actual vapor pressure and 165 rows with missing or invalid VPD.
These rule failures overlap. No complete-weather row fails the wind or
temperature range.

Only 7,758 rows support the clean ML fit. The all-station audit retains 7,760
source rows by the physical rules, but missing model weather limits the fit.
The run does not include gridMET weather for the remaining stations.

## Selective results

Every synthetic condition uses the same 7,758 rows, 84 stations, and 62
proximity groups. OpenET station-macro MAE is 0.851 mm/day in each condition.
Each method's paired 95% interval against OpenET appears in `results.json`.
The intervals use 2,000 proximity-group bootstrap draws with seed 20260922.

| Condition | Gain | SupportGain | MonoGain | AugmentedGain | Uniform | LocalShrinkage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Clean | 0.826 | 0.825 | 0.835 | 0.862 | 0.810 | 0.806 |
| Wind x3.6 | 0.934 | 0.872 | 0.924 | 0.864 | 0.900 | 0.892 |
| Wind x5 | 1.024 | 0.887 | 0.992 | 0.866 | 0.955 | 0.944 |
| Wind x10 | 1.242 | 0.853 | 1.230 | 0.857 | 1.106 | 1.129 |
| Fahrenheit read as Celsius | 1.265 | 0.858 | 1.252 | 0.873 | 1.140 | 1.144 |
| VPD x10 | 3.013 | 0.845 | 2.970 | 0.853 | 2.216 | 2.377 |

All table values are station-macro MAE in mm/day. The model predictions and
acceptance rates for every tested fault are in the saved prediction files.

LocalShrinkage reduces clean MAE by 0.018 mm/day against SupportGain. Its
paired 95% interval is [0.001, 0.037] over 62 groups. This interval is
unadjusted. The one-sided group sign-flip p-value is 0.026, and the Holm
adjusted value is 0.154 across 11 selected comparisons. The result does not
establish a corrected positive finding. LocalShrinkage and Uniform differ by
0.003 mm/day, with paired interval [-0.009, 0.019].

SupportGain improves over Gain as faults grow. At wind x10, its MAE is 0.853
mm/day, compared with 1.242 for Gain. Gain accepts 37.1% of rows, while
SupportGain accepts 1.0%. The paired improvement is 0.389 mm/day, with 95%
interval [0.243, 0.554] and Holm adjusted p-value 0.00055. The same direction
appears at wind x3.6, wind x5, Fahrenheit-as-Celsius, and VPD x10. SupportGain
is a stronger fallback rule under these faults. It does not improve accuracy
on every clean or naturally shifted population.

Monotone constraints do not solve the Gain failure. MonoGain reaches 1.230
mm/day at wind x10, compared with 0.853 for SupportGain. Fault augmentation
stays near OpenET under strong faults, but it scores 0.862 on clean rows and
accepts 14.5% of them. It does not beat SupportGain in the selected fault
comparisons after Holm correction.

## Natural archive fault

The clean screen removes all 32 `manilacotton` rows from training. The
proximity fold also holds out their group. On those 32 source rows, Gain
accepts every correction and scores 22.681 mm/day station MAE. OpenET and
SupportGain both score 1.095 mm/day. SupportGain and AugmentedGain reject
every correction. This is a descriptive result from one station and one
group. It does not provide a multi-group uncertainty estimate.

The Gain model predicts mean improvement of 0.83 mm/day on those rows, while
the realized mean change is -21.59 mm/day. Their mean absolute correction is
21.98 mm/day. Their mean ensemble spread is 39.42 mm/day. The held-out fold's
clean inner 95th percentiles are 1.17 mm/day for correction size and 0.37
mm/day for spread. The corrupted inputs are far outside both ranges.

The Tier 1 selector code already includes log(1 + d5) in Gain. The new run
therefore tests monotone constraints, inner-fold fault augmentation, and local
shrinkage. It also tests wind zero, dropout, seven-day stuck values, and a
training-only day-of-year climatology.

The inspected `station_metadata.xlsx` file lists measurement technique but
has no instrument model or rated accuracy. `variable_explanation.xlsx` lists
units and definitions, not instrument specifications. The run assigns no
additive-noise scale because these sources give no defensible sensor error.

## Figures and records

- [Wind and temperature dose-response](../../../manuscript/arxiv/figures/figure_9_tier1_dose_response.png)
- [Other fault types](../../../manuscript/arxiv/figures/figure_10_tier1_fault_types.png)
- [Gain mechanism and training range](../../../manuscript/arxiv/figures/figure_11_tier1_gain_mechanism.png)
- [Complete method results](results.json)
- Full paired predictions: `predictions_*.csv`.
- [Physical-validity protocol](../../evaluation/ML_TIER1_SELECTIVE_PROTOCOL.md)
- [Run and analysis receipts](receipt.json, analysis_receipt.json)

The protocol hash, code hash, data hashes, seeds, versions, timings, and
fold sizes appear in the receipts. The figures follow the typography, palette,
clean axes, and vector export guidance in the
[figures4papers repository](https://github.com/ChenLiu-1996/figures4papers).
