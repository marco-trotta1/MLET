# Tier 1 natural input violation protocol

Status: fixed before this extension fit. The `manilacotton` outcome is already known and is excluded from the main population.

## Question

Test whether SupportGain limits correction error on other archive rows that fail the fixed physical weather screen.
This analysis is exploratory because the archive and the `manilacotton` outcome were inspected before this protocol.
An invalid input is a physical rule violation, not proof of a sensor defect.

## Population

Use `physical_audit_complete_weather.csv` and its fixed `valid` field. Join its row identifiers to the original complete-weather cohort.
Select every row with `valid == False` and `station != "manilacotton"`.
This rule selects 133 rows from 21 stations and 17 proximity groups. Do not filter rows using outcomes or model predictions.
All 133 rows have complete model inputs and targets. Keep their original values and station groups.

Report the 32 known `manilacotton` rows and all 165 invalid rows as separate descriptive populations.
Report the rows with negative actual vapor pressure separately. Do not pool these populations as independent replications.

## Fixed model and split

Reuse the ten proximity outer folds in `docs/results/ml_transfer/splits.json`.
Fit each three-member network and its selectors on the fixed clean cohort, as in `scripts/ml_tier1_selective.py`.
Use its feature order, seeds, inner partitions, thresholds, and hyperparameters. Do not tune with invalid rows or their targets.
Score an invalid row only with the fold that withholds its proximity group.
Apply the source inputs without a synthetic transform. Keep OpenET as the fallback.

Replay the clean test predictions before analyzing invalid outcomes.
Require matching row identifiers, acceptance masks, and predictions within 1e-8 mm/day of `predictions_clean.csv`.
This tolerance permits CSV serialization differences. Stop if the replay check fails.

## Outcomes

The named contrast is station-macro MAE for Gain minus station-macro MAE for SupportGain on the 133-row population.
A positive value favors SupportGain. Give each station equal weight.
Report a percentile 95% interval from 2,000 paired bootstrap draws over the 17 proximity groups.
Keep each group's stations and rows together. Use seed 20260924.
The interval conditions on the fitted models and selectors. It does not make this archive independent.

Report OpenET, Full, Gain, and SupportGain point MAE, acceptance, and per-group error differences.
Report the all-invalid and negative-vapor subsets descriptively. Report the result without `manilacotton` first.
Report every outcome, including a null or adverse result. Do not choose a different method after inspection.
No p-value is planned. The named contrast has no multi-test p-value family.

## Records

Save predictions, group contributions, a figure, and run and analysis receipts in `docs/results/ml_tier1_natural_violations/`.
Record data, protocol, and code hashes, library versions, seeds, model warnings, and runtime.
Refuse to overwrite completed results.
Use the figures4papers publication workflow for the figure's typography, palette, and vector output.
