# MLET: Incremental Predictive Value of OpenET and an Auditable Reference-Evapotranspiration Outlook

**Manuscript status:** Draft for internal review.

**Evidence status:** The Phase 2 result is independently reproduced. The
complete reference-ETo hindcast remains pending.

## Abstract

Machine Learning Evapotranspiration (MLET) keeps actual ET and reference ETo
as separate evidence paths. The retrospective path uses OpenET and
energy-balance-corrected daily actual ET at 85 stations. The common
station-held-out 10-fold evaluation contains 7,923 station-days. The
preregistered M3 OpenETRidge model has MAE 0.856 mm/day. B2 WeatherRidge has
MAE 1.514 mm/day. The paired station-blocked 95 percent interval for the
baseline-minus-M3 MAE difference is 0.399 to 0.911 mm/day. M2 OpenETRecal has
the lowest descriptive MAE, 0.781 mm/day, without a paired interval.

The outlook path computes GEFSv12 ASCE standardized short-reference ETo and
compares it with published USBR AgriMet ETos. The BOII case is a retrospective
reforecast diagnostic. It contains one issue, one station, and 20 targets.
Forecast MAE is 1.133 mm/day. Fixed prior-years station climatology MAE is
0.505 mm/day. The signed baseline-minus-forecast MAE difference is
-0.628 mm/day, so forecast MAE is higher. Empirical p10-to-p90 coverage is
0.25 against a nominal target of 0.80. Mean band width is 1.453 mm/day. One
bootstrap cluster and fewer than 30 targets per support cell prevent a paired
confidence interval. Full-archive reference-ETo skill remains pending.

## Introduction

Reference ETo describes atmospheric demand for a defined reference surface.
Actual ET depends on crop condition, soil water, and management. MLET therefore
uses separate targets, baselines, source receipts, and claim boundaries.

The completed Phase 2 question is whether OpenET adds value to retrospective
daily actual-ET prediction. The outlook question is whether archived GEFSv12
weather can support a 20-day regional reference-ETo artifact. Neither path
supports a field-scale actual-ET or irrigation claim.

## Methods

### Phase 2 daily actual-ET comparison

The response is energy-balance-corrected daily actual ET. The benchmark
reference ETo is gridMET ETo, not GEFS ETo. The OpenET input is the available
daily OpenET actual-ET estimate.

The primary split is station-held-out 10-fold evaluation. B0 uses 1,555
consecutive-day pairs and remains an oracle-like diagnostic. B1 is one static
pooled training-set mean of the response-to-gridMET-ETo ratio over rows with
positive gridMET ETo. It is not crop-specific or stage-specific. B2 and M3
standardize predictors with training means and standard deviations. Their
ridge penalty is lambda=1. The intercept is the training response mean and is
not penalized. M2 is ordinary least squares with an intercept and slope.

H2 is a preregistered comparison, not a model. It requires at least 10 percent
lower pooled MAE than the better of B1 and B2. Its station-blocked 95 percent
confidence interval for the baseline-minus-M3 difference must be above zero.
M2 has the lowest MAE only among B1, B2, and M1 through M3 on the common
7,923-row sample.

### Reference-ETo outlook

The outlook uses NOAA GEFSv12 retrospective reforecast inputs. The source issue
is 2019-07-03 00Z. The archive became available at
2026-08-04T18:08:54.243122Z. These are separate times. The case was not a
public operational forecast in 2019.

The outlook ETo is GEFS-derived ASCE standardized short-reference ETo. Stored
GEFS wind is measured at 10 m. The pyfao56 routine performs the internal 10 m
to 2 m adjustment. The empirical p10, p50, and p90 values use 11 sorted
members and NumPy linear interpolation between adjacent order statistics. The
p10-to-p90 result is an uncalibrated ensemble quantile band.

The spatial artifact is the exact common 0.5-degree GEFS grid-point subset
across the 0.25-degree early and 0.5-degree late source segments. No
interpolation creates it. The target grid cell 43.50:-116.00 maps to tile
43:-116 and fold 2 through the full SHA-256 digest modulo five.

AgriMet ETos is a published station-derived grass-reference target converted
from inches per day by 25.4. It is not a direct flux measurement or a GEFS
recomputation. Fixed climatology uses all strictly prior years for the same
station and day of year. It is not a learned cross-fold component.

### Implementation and governance

The decode and ETo chain is:

- scripts/decode_gefs_reforecast.py
- src/mlet/sources/gefs_reforecast_batch.py
- src/mlet/sources/gefs_grib.py
- src/mlet/sources/gefs_reforecast.py
- src/mlet/outlook/eto.py

Frozen means fixed before evaluation. Promotion means public operational
release. Validation complete means that every required support cell meets its
target count. Skillful means that the preregistered MAE rule and confidence
interval rule pass. Release review is an independent check before any public
release.

## Results

### Phase 2 result

M3 OpenETRidge reports MAE 0.856 mm/day against 1.514 mm/day for B2
WeatherRidge. The reduction is 43.4 percent. The paired 95 percent interval is
0.399 to 0.911 mm/day. M2 OpenETRecal has the lowest descriptive MAE,
0.781 mm/day. It has no paired interval.

### BOII feasibility diagnostic

The BOII case passes source, identity, checksum, local-day, and target-time
checks. It is a retrospective reforecast diagnostic. The forecast has MAE
1.133 mm/day. Prior-years station climatology has MAE 0.505 mm/day. The
baseline-minus-forecast difference is -0.628 mm/day, so the forecast is worse.
Empirical p10-to-p90 coverage is 0.25. The nominal target is 0.80. Mean band
width is 1.453 mm/day. The case has one bootstrap cluster and 20 targets.
It is below the 30-target support rule. No paired confidence interval is
identified.

## Limitations

- The full 365-issue GEFS and AgriMet outcome archive is absent.
- Full-archive reference-ETo skill remains pending.
- Historical location evidence covers 19 stations.
- The weather artifact has grid points, not field boundaries or area weights.
- The Phase 2 result does not measure future forecast performance.
- The BOII uncertainty is not estimable with one bootstrap cluster.

## Conclusions

MLET reports a narrow retrospective OpenET result and a separate reference-ETo
diagnostic. The BOII diagnostic is negative against fixed prior-station
climatology and lacks support for a skill claim. No operational promotion is
made. A complete archive and release review are required.

## References

See references.bib.
