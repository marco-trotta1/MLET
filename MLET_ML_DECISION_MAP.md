# MLET ML Reliability Decision Map

Goal: build a defensible two-to-seven-day root-zone soil-moisture forecasting
pipeline, without synthetic training data or unsupported accuracy claims.

Known facts:

- The source ET validator passes 36 tests when tested from this checkout with
  `PYTHONPATH=src`; the default test command currently imports a stale editable
  `mlet` package from `/private/tmp`.
- No MLET ingestion, training, OpenET-assimilation experiment, or evaluation
  harness exists yet.
- The next model must be judged against persistence and a calibrated
  forecast-driven water-balance baseline using time- and field-withheld splits.

## #1: Is there enough measured field data to begin model development?

Type: Grilling

### Question

What real, time-aligned data is available now for each field and day: observed
root-zone soil moisture, OpenET ET, weather, irrigation records, and static
soil/crop attributes? Include the approximate number of fields and seasons.

### Answer

Open. This determines whether the next work is a data-provenance/ingestion
pipeline or acquiring and instrumenting a validation dataset.

## #2: Make local verification hermetic

Type: Prototype

### Question

How should the project guarantee that tests and future training commands use
the checked-out source and a pinned environment, never an unrelated editable
install?

### Answer

Open.

## #3: Freeze the benchmark before training

Blocked by: #1, #2
Type: Research

### Question

What exact target construction, latency rules, field/time holdouts, leakage
checks, baselines, metrics, and promotion thresholds are fixed before any
OpenET comparison?

### Answer

Open.
