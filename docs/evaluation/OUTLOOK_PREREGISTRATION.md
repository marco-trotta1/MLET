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

## Executable release-gate receipt

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

The report contains sample count, MAE, RMSE, bias, empirical closed-interval
coverage, and interval width by layer/lead, month, season, and spatial block.
It writes an adjacent `validation.json` from an internally issued,
hash-bound evaluation receipt (not a public report object) with the
authoritative `promotion` boolean and every blocking reason. Promotion requires
nonzero sample count and
recorded coverage for leads 1–20 of ETo, the well-watered ETa scenario, and
the no-irrigation ETa scenario. Conditional ETa targets must use their named
scenario target kinds; they cannot be recast as observed actual ET.

`fixture_non_scientific: true` is a permanent release blocker. It exists only
to test software behavior and is never a result, a hindcast, or evidence for a
forecast claim. This document reports no numerical skill result until an
archived non-fixture data set satisfies all of the gates above.

## External promotion authority

Passing computational gates does not itself authorize a public promotion. The
evaluator canonicalizes the verified forecast, manifest, target, receipt-byte
hashes, case/run identifiers, classification, fold/cutoff, and scenario
evidence into an `evaluation_digest`. An external release authority must attest
to that digest **and** the reconstructed report digest with Ed25519. The
accepted identity, key ID, algorithm, and public key are committed in
`src/mlet/outlook/promotion_authority.json`. MLET has no private key, no
environment-variable key override, and no `attest-hindcast-outlook` signing
command. Changing the authority requires a reviewed repository change to that
public verifier configuration.

The evaluator exposes a verification request only; it does not sign it:

```python
from pathlib import Path
from mlet.outlook.hindcast import build_promotion_attestation_request

request = build_promotion_attestation_request(Path("ARCHIVED_CASES.json"))
```

The external release authority independently checks the archived evidence,
then signs exactly these binary bytes with its offline/private Ed25519 key:

```text
ASCII "MLET-IDAHO-OUTLOOK-HINDCAST-ATTESTATION" + 0x00 + 0x01
+ 32 raw bytes of evaluation_digest (hex-decoded)
+ 32 raw bytes of report_sha256 (hex-decoded)
```

It returns a `promotion_attestation` object with exactly
`schema_version`, `algorithm`, `key_id`, `evaluation_digest`, `report_sha256`,
and base64 `signature`. The operator embeds that object in the evidence bundle
and reruns `hindcast-outlook`. The evaluator and validation writer independently
reconstruct the report and digest, require the exact pinned key identity, and
verify the signature. Missing, altered, replayed, cross-bundle, or
attacker-selected-key attestations remain non-promotable. Software fixtures
have no signing path and remain non-promotable.
