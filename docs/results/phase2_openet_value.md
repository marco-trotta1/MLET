# Phase 2 — OpenET-value results

Independent reproduction completed from the checksum-verified Phase 2 source archives.

## Station-held-out model comparison

Station count: 85

| model | MAE (mm/day) | RMSE (mm/day) | bias (mm/day) | n |
|---|---:|---:|---:|---:|
| B0_Persistence | 0.350 | 0.572 | 0.058 | 1555 |
| B1_CropCoefficient | 1.532 | 2.005 | 0.149 | 7923 |
| B2_WeatherRidge | 1.514 | 2.687 | -0.098 | 7923 |
| M1_OpenETDirect | 0.784 | 1.066 | 0.154 | 7923 |
| M2_OpenETRecal | 0.781 | 1.060 | 0.005 | 7923 |
| M3_OpenETRidge | 0.856 | 1.386 | -0.013 | 7923 |

## OpenET value comparison

Best OpenET-free model: B2_WeatherRidge
MAE reduction: 43.4%
MAE delta: 0.658 mm/day; 95% CI [0.399, 0.911] mm/day.
