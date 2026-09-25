# Tier 1 daily GridMET stuck-wind correction

Status: exploratory. The earlier stuck-wind outcomes were inspected before
the implementation defect was found.

## Correction

The old transform changed wind for only 137 of 7,842 test rows. It grouped
sparse evaluation dates, so it did not model a daily seven-day hold.

The corrected transform uses daily GridMET wind. It starts non-overlapping
seven-day blocks at each station-year file's first date. It uses the first
wind value in each block for every evaluation date in that block.

The correction changes 6,248 of 7,842 test wind inputs. This is 79.7% using
a tolerance of 1e-8 m/s. The corrected run uses the same cohort, splits,
test years, ten-member ensembles, seeds, and model settings as the original.
It uses the corrected fault in inner augmentation and outer evaluation.
This remains a synthetic input fault. It is not an observed sensor failure.

## Results

Each condition has 7,842 rows from 101 stations and 64 spatial groups.
Station-macro MAE uses mm/day. Acceptance is station-weighted.

| Method | Clean MAE | Clean acceptance | Stuck-wind MAE | Stuck-wind acceptance |
| --- | ---: | ---: | ---: | ---: |
| OpenET | 0.854 | not applicable | 0.854 | not applicable |
| Gain | 0.806 | 75.6% | 0.836 | 75.0% |
| SupportGain | 0.801 | 73.3% | 0.828 | 71.6% |
| MonoGain | 0.811 | 76.6% | 0.831 | 74.5% |
| AugmentedGain | 0.855 | 19.6% | 0.860 | 16.9% |

Positive change favors the first method. Each interval uses 2,000 paired
group-bootstrap draws over 64 groups. These intervals are descriptive. The
analysis reports no p-values or multiplicity adjustment.

| Condition | Method | Baseline | MAE change (95% interval) | Seed |
| --- | --- | --- | ---: | ---: |
| Stuck wind | SupportGain | Gain | 0.0077 [-0.0024, 0.0174] | 20260925 |
| Stuck wind | MonoGain | SupportGain | -0.0024 [-0.0133, 0.0085] | 20260926 |
| Stuck wind | AugmentedGain | SupportGain | -0.0313 [-0.0737, -0.0003] | 20260927 |
| Clean | AugmentedGain | SupportGain | -0.0542 [-0.0875, -0.0264] | 20260928 |

The corrected SupportGain point estimate is lower than Gain. Its interval
includes zero. MonoGain does not improve on SupportGain by point estimate.
AugmentedGain has higher error than SupportGain in both reported conditions.
Treat every contrast as exploratory.

## Records

- [Correction protocol](../../evaluation/ML_TIER1_GRIDMET_STUCK_CORRECTION_PROTOCOL.md)
- [Run receipt](receipt.json)
- [Analysis receipt](analysis_receipt.json)
- [Exploratory analysis](exploratory_analysis.json)
- [Daily stuck-wind inputs](wind_stuck_daily_inputs.csv)
- Full predictions: `predictions_*.csv`.

Rebuild the run and analysis from the full repository root:

```sh
python3 scripts/run_ml_tier1_gridmet_stuck_correction.py
python3 scripts/analyze_ml_tier1_gridmet_stuck_correction.py
```
