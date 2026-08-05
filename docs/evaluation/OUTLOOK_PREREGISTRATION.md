# Idaho regional ET outlook preregistration

**Frozen:** 2026-07-16
**Applies to:** the first Idaho-only, native-weather-grid, 20-day outlook.
**Status:** a prospective evaluation protocol; no hindcast result is reported
in this document.

## Amendment (2026-07-29): ETo-only manuscript evaluation

This amendment applies before the first real archived ETo evaluation. It
supersedes earlier text in this document that makes ETa scenarios release-gate
targets.

MLET formally evaluates only `eto_mm`, the 20-day weather-driven reference ETo
forecast. `potential_et_c_mm`, `eta_well_watered_mm`, and
`eta_no_irrigation_mm` are conditional projections. They are not independently
validated forecasts. `eta_analysis_mm` is a delayed historical analysis. It is
not a forecast target.

The ETo target is published daily AgriMet `ETos`, the ASCE-EWRI grass-reference
value. The source value is in inches per day. MLET converts it to millimeters
with the exact factor 25.4. MLET does not recompute this target from forecast
weather inputs.

The primary baseline is a fixed station-specific, day-of-year ETo climatology.
For each evaluated target, use every strictly prior calendar year for that
station and day of year. The evaluated year is absent. Do not remove the
station because its target grid cell is held out. Spatial fold exclusion
applies only to learned or tuned components. Report p50 MAE,
RMSE, and bias; p10-p90 coverage and width; and mean pinball loss over p10,
p50, and p90. Report paired comparison with the baseline. Use a paired
bootstrap that clusters by issue date and station.
The implementation uses seed `20260731` and 1,000 replicates. It reports the
2.5th and 97.5th percentiles of the paired MAE-improvement distribution. A
cell with fewer than two issue-date and station clusters reports no interval.

Require at least 30 paired station-date targets for each reported lead, season,
and spatial-fold cell. If support is lower, report the cell and mark the
evaluation incomplete. Do not fill missing target values.

`Validation complete` means that MLET completed this preregistered evaluation.
It does not require a fixed skill threshold. State that the forecast is
`skillful` only where the preregistered paired confidence interval for baseline
improvement excludes zero.

Use evidence-bundle schema version 4 and ETo-target schema version 2. A v4 case
requires forecast, target, source, and holdout receipts. It does not require
water, crop, precipitation, or soil scenario receipts. A forecast candidate
must state `research_candidate`, `not_promoted`, and `evaluation_pending`. It
must not claim validation before the evaluator runs.

Build each historical issue as one self-contained v4 evidence bundle. Before
scoring, copy every case into one archive root and rewrite every receipt path
below that root. Do not score a bundle that depends on files in a staging
directory.

## Product quantities and claim boundary

Evaluation keeps four layers separate: forecast `eto_mm`; ample-water
`potential_et_c_mm`; delayed, observed `eta_analysis_mm`; and conditional
`eta_well_watered_mm` and `eta_no_irrigation_mm`. `eta_analysis_mm` is an
observed satellite analysis with an explicitly recorded lag, not a future
forecast. The conditional layers are evaluated only as scenarios under their
recorded assumptions; neither is treated as a generic future actual-ET target.

## Issue-time cutoff and forecast range

For an operational historical issue, the input cutoff is the recorded
`issued_at_utc`. An input is eligible only when immutable source metadata shows
that it was issued or observed at or before that cutoff. The run receipt stores
source issue, observation, and valid times, the source revision, an input
checksum, and the local retrieval timestamp. A later archive retrieval does
not make an operational input eligible.

The BOII GEFSv12 result is a retrospective reforecast diagnostic. Its receipt
records the historical `source_issue_at` and the later `archive_available_at`
separately. The archive availability is `2026-08-04T18:08:54.243122Z`, so this
case does not claim operational issue-time availability. The retrospective
chronology checks the source issue against the candidate issue and does not
reject the case only because the archive was retrieved later.

For OpenET, each selected immutable model/version row records a strict-UTC
`source_available_at` no later than `issued_at`; the observation date must be a
completed Idaho-local day strictly before the Idaho-local issue date. Latency
is whole Idaho-local days from that issue date, not from a potentially later
archive retrieval. For CDL, the
archived intersection table records a checksum plus source year, layer version,
pinned official legend version, release time, and upstream URI. The release
time must be no later than `issued_at`; no unpinned legend year is eligible.

The forecast target range is lead days 1 through 20 inclusive, each mapped to
an Idaho local `valid_date`. The frozen day boundary is `America/Boise`, using
the IANA MST/MDT rule at the issue instant: lead 1 is the day after the Idaho
local date of the strict-UTC issue timestamp and leads 2–20 are consecutive
Idaho local dates. GEFS and every daily target/ETa aggregate must explicitly
state that same Idaho-local aggregation label; UTC-day or unspecified-day
aggregates are invalid inputs. Daily outputs retain `p10`, `p50`, and `p90`; all
metrics are computed by lead day before any pooled summary is reported. See the
2026-07-27 amendment below for the probabilistic-skill terminology used when
only those published quantiles are available.

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
- an operational input, a late OpenET analysis, or a later annual crop layer
  crosses the issue-time cutoff;
- a lead day, quantile, grid reference, or scenario assumption is missing;
- the `p10`–`p90` intervals cannot be evaluated for empirical coverage; or
- a held-out spatial block or season is used by a fitted or tuned component.

On failure, the run receipt must identify the failed gate and the public map
must not carry a “validated” claim. A passed software test alone is not a
scientific validation. A public validated-performance statement is permitted
only after a complete preregistered hindcast passes these gates and publishes
its manifests, metrics, and limitations.

## Legacy full-product release-gate receipt

The following section documents the retained version-3 full-product release
path. It is not the manuscript ETo evaluation path. Use schema-v4 ETo evidence,
`mlet outlook hindcast`, and the contract above for the manuscript. The flat
`mlet hindcast-eto` command remains a compatibility alias.

The frozen evaluator is invoked with:

```bash
python3 -m mlet hindcast-outlook \
  --cases ARCHIVED_CASES.json \
  --out docs/results/idaho_outlook_hindcast.md
```

The input is a version-3 **evidence bundle**, not a table of caller-supplied
scores. It declares `evidence_classification` as either `real_archived` or
`software_fixture`, plus a versioned, checksummed provenance receipt. Every
case names a strict-UTC `issue_time`; the exact forecast `run_id`; bytes and
SHA-256 digests for its `manifest.json` and `outlook.json`; and a separate
target-artifact path, URI, version, checksum, and availability timestamp. The
target artifact embeds the same URI/version/availability receipt inside its
hashed bytes, so changing a receipt time in the bundle cannot recast a target
as historically available. The
evaluator verifies the manifest/run/artifact identity, then reconstructs
quantiles from `outlook.json` and truth from the target bytes. Inline `rows`,
even if perfect, are rejected and can never promote a release.

Each case names separate, content-addressed JSON receipt artifacts for every
source, the fold/cutoff declaration, and each water, crop, precipitation, and
soil assumption. Their exact bytes and SHA-256 hashes are part of the canonical
evaluation digest. Every receipt carries immutable URI, version, checksum and
availability fields plus the case and forecast run identifiers. Inline-only
source availability, folds, cutoffs, or scenario declarations are rejected.
A late source, target, assumption, fold/season overlap, or cutoff reaching a
held-out target blocks promotion. The release gate requires all five spatial
folds and all four calendar seasons, as well as lead-day coverage. An offset,
naive, or otherwise ambiguous timestamp is invalid.

The exact forecast contract must say `fixture_non_scientific: false`,
`publication_classification: "production"`, and
`validation_status: "validated"`. Missing, non-boolean, fixture, or other
classification states are permanent promotion blockers.

The local Markdown report contains sample count, MAE, RMSE, bias, empirical closed-interval
coverage, and interval width by layer/lead, month, season, and spatial block.
It is a diagnostic only and never says that gates passed, that a result is
validated, or that it is production-ready—even when a caller constructs or
mutates its public aggregate object. The command writes adjacent
`validation.json` and `authority_request.json` from a
reconstructed, hash-bound evaluation candidate (not a public report object).
Both local artifacts always carry `promotion: false` and every blocking reason.
The request is eligible for external release review only when its sole blocker
is `requires_separately_trusted_release_authority`. Computational eligibility
requires nonzero sample count and
recorded coverage for leads 1–20 of ETo, the well-watered ETa scenario, and
the no-irrigation ETa scenario. Conditional ETa targets must use their named
scenario target kinds; they cannot be recast as observed actual ET.

`fixture_non_scientific: true` is a permanent release blocker. It exists only
to test software behavior and is never a result, a hindcast, or evidence for a
forecast claim. This document reports no numerical skill result until an
archived non-fixture data set satisfies all of the gates above.

## External promotion authority

Passing computational gates does not authorize public promotion. MLET is inside
the evaluator threat boundary: a process able to modify its Python memory,
environment, code, or output directory must never be able to make MLET emit a
true promotion. Accordingly, MLET has no signing key, public-key verifier,
authority configuration, environment-variable override, or local promotion
command. It cannot create, verify, or publish a true promotion receipt.

For a qualifying archived data set, MLET canonicalizes the verified forecast,
manifest, target, receipt-byte hashes, case/run identifiers, classification,
fold/cutoff, and scenario evidence into an `evaluation_digest`. It then writes
`authority_request.json`, a canonical candidate artifact whose bytes include
that digest, the case hashes, and the hash of the reconstructed candidate
report. The candidate remains `promotion: false`:

```python
from pathlib import Path
from mlet.outlook.hindcast import build_release_authority_request

request = build_release_authority_request(Path("ARCHIVED_CASES.json"))
```

The separately trusted release authority operates outside this repository and
outside the MLET evaluator process. It independently retrieves the immutable
archive and candidate request; checks their SHA-256 bindings, frozen gates, and
publication policy; and creates and publishes a distinct
`separately_trusted_release_validation_receipt` in its own controlled release
system. That external receipt must identify the exact `evaluation_digest`, the
candidate-report hash, its release-authority identity, decision time, and an
auditable signature or equivalent approval record. It is never embedded into
the evidence bundle for MLET to turn into local `promotion: true`.

The public release workflow is therefore: (1) archive the exact evidence and
MLET candidate, (2) obtain a separately trusted release receipt, and (3) have
the external release system publish the promoted product together with both
artifacts. A local qualifying archive exits with code 1 as a release candidate;
fixtures also exit with code 1 but remain permanently non-scientific and are
not eligible for external release review.

## Amendment (2026-07-27): probabilistic skill terminology for published quantiles

Probabilistic skill is reported as the **mean pinball loss over the p10, p50, and
p90 levels**, not as the continuous ranked probability score. CRPS integrates the
pinball loss over all quantile levels; the outlook contract emits three
quantiles, so CRPS is not identified from the published output. Mean pinball loss
over the emitted levels is a proper scoring rule and a discrete approximation to
CRPS, and it is what the code computes (`mlet.evaluate.mean_pinball_loss`).

Any comparison against a point forecast scores that forecast with a degenerate
interval whose three quantiles all equal its point value, so that the interval
arm is not credited merely for emitting an interval.

This dated amendment narrows the probabilistic-skill claim to mean pinball loss
over the emitted levels. It changes no threshold, cutoff, split, or gate. The
coverage target and tolerance are unchanged.

## Static research-candidate rendering

`python3 -m mlet publish-outlook --run OUTPUT_ROOT/RUN_ID` renders a
self-contained `index.html`, `outlook.geojson`, `summary.json`, and
`serve-contract.json` from descriptor-verified immutable run bytes. The
renderer is inside the same evaluator threat boundary and always writes
`promotion: false`, `promotion_status: "not_promoted"`, and
`validation_status: "validation_pending"`; a source receipt, sibling
`validation.json`, environment value, or caller mutation cannot make its output
state promoted or validated. It returns exit code 1 after writing a readable
research candidate, or 2 when the run cannot be read.

The renderer writes its four artifacts into a private, fsynced generation under
the trusted output root and atomically exposes the completed candidate handle.
An interrupted write therefore cannot leave a public partial candidate; a
subsequent attempt may publish the previously unclaimed final name.

The static interface exposes the five named layers, issue time, ETa observation
date, p10/p50/p90 uncertainty, source run ID, and the regional—not field-level
warning. It uses source weather-grid reference points only when the serving
contract carries them; it never invents field boundaries or grid-cell polygons.
Until source-grid areas are included in the serving contract, `summary.json`
contains an explicitly labelled equal-cell descriptive mean rather than a
statewide area-weighted claim. Fixture rendering is visibly non-scientific and
is never a forecast claim or a scientific result.
