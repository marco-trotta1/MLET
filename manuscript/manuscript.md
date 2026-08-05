# MLET: OpenET value and an auditable reference-ET outlook

**Manuscript status:** Draft for internal review.

**Evidence status:** The Phase 2 result is independently reproduced. The ETo
outlook software and source contracts are implemented. The full ETo hindcast
is not yet complete.

## Abstract

Evapotranspiration estimates support water management, crop studies, and
forecast evaluation. MLET separates two questions that require different
targets. The first question asks whether OpenET improves daily actual-ET
prediction at field-withheld flux stations. The second asks whether archived
ensemble weather can support a 20-day regional reference-ET outlook.

The Phase 2 record reports a field-withheld comparison on a common complete
subset of 85 stations and 7,923 station-days. The best OpenET-inclusive model
has a reported MAE of 0.856 mm/day. The best OpenET-free weather model has a
reported MAE of 1.514 mm/day. The reported reduction is 43.4 percent. The
paired 95 percent confidence interval for the MAE difference is 0.399 to
0.911 mm/day. The independent reproduction receipt matches the committed
result to three decimal places and binds the source archives by checksum.

The outlook evaluates only weather-driven ASCE short-reference ETo. It uses
archived GEFS reforecast inputs and published USBR AgriMet ETos targets. The
software records source times, checksums, station identity, grid identity, and
layer-level claim status. Conditional crop ET and ETa scenarios remain outside
the formal validation target. Historical station evidence now supports 19
stations through the acquired target window, with BOII as the full feasibility
case. The full outcome archive is still required before ETo skill is reported.

## Introduction

Evapotranspiration is not one measurable quantity with one universal forecast
target. Reference ETo describes atmospheric demand for a defined reference
surface. Actual ET depends on crop condition, soil water, and management.
Confusing these quantities can turn a regional weather product into an
unsupported field irrigation claim.

MLET therefore uses separate evidence paths. Phase 2 tests the incremental
value of OpenET for retrospective daily actual-ET prediction. The outlook
path tests a 20-day weather-driven reference-ET artifact. Each path has its own
target, baseline, source receipt, and claim boundary.

The project has two practical goals. First, it should provide a reproducible
research artifact that another analyst can inspect and rebuild. Second, it
should provide a manuscript-ready record that reports both positive and
negative evidence without changing the protocol after results are observed.

## Methods

### Phase 2 daily actual-ET comparison

The Phase 2 benchmark joins published OpenET model ET with a public flux-tower
collection. The join uses exact station and date keys. The target is the
energy-balance-corrected daily ET value. The uncorrected ET column is not
scored.

The field-withheld comparison reports persistence, a crop-coefficient baseline,
a weather-only ridge model, and three OpenET-inclusive models. The common
complete subset contains 85 stations and 7,923 station-days. The result record
stores the source manifest digest and the fixed random seed.

The primary comparison is the best OpenET-inclusive model against the best
OpenET-free model. The report uses MAE, RMSE, signed bias, and a paired
confidence interval for the MAE difference. This comparison is retrospective.
It is not a 20-day forecast test.

### ETo outlook

The outlook target is published daily USBR AgriMet ETos. ETos is ASCE-EWRI
grass-reference ETo. The source value is published in inches per day. MLET
converts it to millimeters with the exact factor 25.4. MLET does not calculate
the target from its forecast weather path.

The protocol uses archived GEFS reforecast inputs. Weekly issues occur on
Wednesday 00Z from 2013-01-02 through 2019-12-25. Each issue provides 11
members through lead day 35. The ETo outlook uses leads 1 through 20. The lead
dates use the Idaho local calendar day in the `America/Boise` time zone.

The primary baseline is station-specific day-of-year climatology. The baseline
excludes the evaluated year. The frozen spatial fold controls forecast
evaluation, while prior target-station history remains available to its
station-specific baseline. The evaluator reports
MAE, RMSE, signed bias, p10 to p90 coverage, interval width, and mean pinball
loss. It reports support by lead, season, and spatial fold. It requires at
least 30 paired station-date targets in each reported cell. Paired confidence
intervals use 1,000 deterministic bootstrap replicates clustered by issue date
and station. A cell with fewer than two clusters reports no interval.

### Provenance and claim status

Every real candidate records source URI, source version, retrieval time, source
availability, and checksum. A forecast candidate has the status
`research_candidate`, `not_promoted`, and `evaluation_pending`.

The current USBR station snapshot records 265 stations and 52 Idaho stations.
It does not prove that a coordinate applies to a historical target date. The
historical audit accepts 19 station pages and dated map evidence. The target
adapter rejects stations without this history.

The formal hindcast target is `eto_mm`. `potential_et_c_mm` is a conditional
crop-ET projection. `eta_analysis_mm` is a delayed historical analysis.
`eta_well_watered_mm` and `eta_no_irrigation_mm` are conditional scenarios.
None of these layers can be relabeled as an unconditional actual-ET forecast.

## Results

### Phase 2 result

The machine-readable result is in
[`../docs/results/phase2_openet_value.json`](../docs/results/phase2_openet_value.json).
The generated table is in
[`../docs/results/phase2_openet_value.md`](../docs/results/phase2_openet_value.md).

| Model | MAE (mm/day) | RMSE (mm/day) | Bias (mm/day) | n |
|---|---:|---:|---:|---:|
| B2 WeatherRidge | 1.514 | 2.687 | -0.098 | 7,923 |
| M1 OpenETDirect | 0.784 | 1.066 | 0.154 | 7,923 |
| M2 OpenETRecal | 0.781 | 1.060 | 0.005 | 7,923 |
| M3 OpenETRidge | 0.856 | 1.386 | -0.013 | 7,923 |

The preregistered H2 model is M3 OpenETRidge. Its MAE is 0.856 mm/day versus
1.514 mm/day for B2 WeatherRidge. The reduction is 43.4 percent. The paired
95 percent confidence interval is 0.399 to 0.911 mm/day. M2 OpenETRecal has
the lowest descriptive MAE, 0.781 mm/day, but it is not the H2 arm. The
independent reproduction receipt confirms the result and its source hashes.

### ETo outlook result

No full ETo hindcast result is reported in this draft. The 2019-07-03
feasibility case passes the GEFS transfer, version-2 decode, AgriMet target,
station-history, grid-match, checksum, and issue-time checks. The full GEFS
and AgriMet outcome archive remains unassembled. This is a data gate, not
evidence of forecast failure.

The ETo result section will be generated from the immutable result record. It
will report the outcome even if the forecast does not improve on climatology.
It will not use a skill threshold to define whether the evaluation is complete.

## Discussion

The Phase 2 record supports a narrow retrospective statement. OpenET-inclusive
models report lower daily actual-ET error than the best OpenET-free model in
the recorded field-withheld comparison. The result does not establish skill
for a future weather forecast, a soil-water forecast, or an irrigation decision.

The outlook artifact addresses a different problem. Its value is auditability:
the forecast target, source cutoff, station identity, mapped grid identity, and
claim status remain visible in machine-readable files. This structure permits a
later hindcast without changing the target definition after seeing outcomes.

The station audit shows why historical metadata matters. A current coordinate
can differ from an earlier station position. The ETo target path therefore
fails closed when a historical location segment is missing. This protects the
manuscript from a silent station move.

The project does not require an OpenET key for the ETo manuscript path. It also
does not require Irrigant access to complete the research artifact or write the
methods and limitations sections. Those integrations are future work.

## Limitations

- The Phase 2 result is independently reproduced from checksum-bound archives.
- The ETo hindcast has no full outcome result in this draft.
- Historical location evidence covers 19 stations, not every current station.
- The outlook is a regional weather-grid artifact. It is not field-scale
  validation.
- Conditional ETc and ETa layers are not formal forecast targets.
- The project does not test irrigation recommendations or operational release.

## Conclusions

MLET now has a reproducible artifact boundary for two distinct ET questions.
The Phase 2 record provides a claim-limited historical result. The outlook
software provides an ETo-only candidate path with strict provenance checks.

The manuscript can be written now around the methods, reproduced Phase 2
evidence, artifact design, and explicit ETo status. The ETo skill result must
be inserted only from the generated immutable result record after the full
archive gate passes.

## References

See [`references.bib`](references.bib).
