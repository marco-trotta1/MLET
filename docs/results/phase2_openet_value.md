# Phase 2 — OpenET-value results

Stations: 85

## Field-withheld

| model | MAE (mm) | RMSE (mm) | bias (mm) | n |
|---|---:|---:|---:|---:|
| B0_Persistence | 0.350 | 0.572 | 0.058 | 1555 |
| B1_CropCoefficient | 1.532 | 2.005 | 0.149 | 7923 |
| B2_WeatherRidge | 1.514 | 2.687 | -0.098 | 7923 |
| M1_OpenETDirect | 0.784 | 1.066 | 0.154 | 7923 |
| M2_OpenETRecal | 0.781 | 1.060 | 0.005 | 7923 |
| M3_OpenETRidge | 0.856 | 1.386 | -0.013 | 7923 |

## H2 — OpenET value

Best OpenET-free model: B2_WeatherRidge
MAE reduction: 43.4%
MAE delta: 0.658 mm; 95% CI [0.399, 0.911]

**OpenET-value decision:** OpenET adds daily-ET value (>=10% MAE reduction, CI excludes 0)

## Stratified H2

- Croplands: B1_CropCoefficient; reduction 34.7%; CI [0.115, 0.832].
- Non-Croplands: B2_WeatherRidge; reduction 41.3%; CI [0.172, 0.828].

## Time-withheld

This parallel split trains through 2018 and tests from 2019. It is descriptive and does not change the pre-registered primary decision.

| model | MAE (mm) | RMSE (mm) | bias (mm) | n |
|---|---:|---:|---:|---:|
| B0_Persistence | 0.505 | 0.765 | 0.074 | 168 |
| B1_CropCoefficient | 1.755 | 2.281 | -0.717 | 649 |
| B2_WeatherRidge | 1.835 | 2.362 | -1.020 | 649 |
| M1_OpenETDirect | 0.795 | 1.045 | -0.073 | 649 |
| M2_OpenETRecal | 0.849 | 1.128 | -0.331 | 649 |
| M3_OpenETRidge | 0.848 | 1.111 | -0.338 | 649 |