# Idaho regional ET outlook preregistration

**Frozen:** 2026-07-16
**Applies to:** the first Idaho-only, native-weather-grid, 20-day outlook.
**Status:** a prospective evaluation protocol; no hindcast result is reported
in this document.

## Product quantities and claim boundary

Evaluation keeps four layers separate: forecast `eto_mm`; ample-water
`potential_et_c_mm`; delayed, observed `eta_analysis_mm`; and conditional
`eta_well_watered_mm` and `eta_no_irrigation_mm`. `eta_analysis_mm` is an
observed satellite analysis with an explicitly recorded lag, not a future
forecast. The conditional layers are evaluated only as scenarios under their
recorded assumptions; neither is treated as a generic future actual-ET target.

## Issue-time cutoff and forecast range

For every historical issue, the input cutoff is the recorded `issued_at_utc`.
An input is eligible only when immutable source metadata demonstrates that the
input was issued or observed at or before that cutoff. A weather forecast may
have a valid date after the cutoff, but its forecast issue must be no later than
the cutoff. The run receipt stores source issue/observation/valid times, the
source revision, an input checksum, and the local retrieval timestamp. An
archived file may be retrieved after the historical issue; that later retrieval
does not make its content eligible. A later reanalysis, later crop map, or
satellite value may not be substituted into a historical issue unless it was
demonstrably available then.

For OpenET, each selected immutable model/version row records a strict-UTC
`source_available_at` no later than `issued_at`; the observation date must be a
completed day strictly before the issue date. Latency is whole days from the
issue date, not from a potentially later archive retrieval. For CDL, the
archived intersection table records a checksum plus source year, layer version,
pinned official legend version, release time, and upstream URI. The release
time must be no later than `issued_at`; no unpinned legend year is eligible.

The forecast target range is lead days 1 through 20 inclusive, each mapped to
an Idaho local `valid_date`. Daily outputs retain `p10`, `p50`, and `p90`; all
metrics are computed by lead day before any pooled summary is reported.

## Holdouts

Spatial performance is assessed with geographically blocked, not random-cell,
holdouts. Grid-cell centers are assigned to fixed one-degree latitude-longitude
tiles using `floor(latitude)` and `floor(longitude)`. A tile's fold is
`sha256("idaho-outlook-v1:{tile_lat}:{tile_lon}") mod 5`; all cells in a held-out
fold are absent from calibration, tuning, and learned-residual fitting. Tile
coordinates, fold assignments, and the exact Idaho boundary source are emitted
in each hindcast manifest.

Seasonal generalization is assessed with four complete calendar-season
holdouts: DJF, MAM, JJA, and SON. For a held-out season, no target date from
that season may be used to fit, calibrate, select, or tune a data-driven
component. If a method has no fitted component, the seasonal split is still
reported as a data-availability and diagnostic stratification.

## Reference quantities and metrics

### ETo

Where an independently available station meteorological record supports an
ASCE short-reference calculation, it is the ETo reference. It must not be a
repackaging of the forecast input being scored. For each lead day and holdout,
report `p50` MAE, RMSE, and signed bias in `mm/day`, plus empirical coverage of
the closed `p10`–`p90` interval and its mean width. Do not call station
comparisons field-scale validation.

### Observed ETa and conditional scenarios

`eta_analysis_mm` is compared only with a later-available observed ETa analysis
that honors its source lag. Report MAE, RMSE, and signed bias in `mm/day` as an
intercomparison with that observed satellite product, not as field ET ground
truth. For the two conditional scenarios, report the same quantities only for
cases whose water, crop, precipitation, and soil assumptions are fully
available in the receipt. Scenario interval coverage is computed against the
corresponding declared scenario target; it is not evidence for an unconditional
actual-ET prediction.

## Failure conditions and reporting rule

A hindcast fails when any of the following occurs:

- an input lacks a source version, checksum, or eligible issue-time record;
- a future value, a late OpenET analysis, or a later annual crop layer crosses
  the issue-time cutoff;
- a lead day, quantile, grid reference, or scenario assumption is missing;
- the `p10`–`p90` intervals cannot be evaluated for empirical coverage; or
- a held-out spatial block or season is used by a fitted or tuned component.

On failure, the run receipt must identify the failed gate and the public map
must not carry a “validated” claim. A passed software test alone is not a
scientific validation. A public validated-performance statement is permitted
only after a complete preregistered hindcast passes these gates and publishes
its manifests, metrics, and limitations.
