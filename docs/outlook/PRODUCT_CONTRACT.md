# Idaho regional ET outlook: product contract

**Status:** frozen product definition; implementation and hindcast validation
remain pending.
**Domain:** Idaho only.
**Audience:** public users who need a regional outlook and researchers who need
a fully inspectable artifact contract.

## Purpose and resolution

MLET's first public outlook is a no-setup **regional Idaho** map of
evapotranspiration-related quantities. It uses the native grid of the weather
forecast source. A map cell is a weather-grid representation, not a field
measurement. The product therefore does not make field-scale claims and does
not provide an irrigation recommendation or a field-specific irrigation
prescription.

Every issue contains 20 daily lead dates. Forecast quantities retain daily
`p10`, `p50`, and `p90` values in millimeters per day (`mm/day`); the product
does not reduce uncertainty to one unqualified deterministic value. `issued_at`
is recorded in UTC, each forecast `valid_date` is an Idaho local calendar date,
and the source issue time and source valid time are retained in the run receipt.

## Four deliberately separate layers

The map and all machine-readable artifacts use the following names verbatim.
They have different meanings, source paths, and eligible timestamps.

| Artifact name | Meaning | Time semantics | Units |
|---|---|---|---|
| `eto_mm` | weather-driven ASCE short-reference ET forecast | future daily forecast from ensemble weather members | `mm/day` |
| `potential_et_c_mm` | `Kc × ETo` under ample-water conditions | future daily, conditional on the crop-coefficient assumption | `mm/day` |
| `eta_analysis_mm` | latest observed-date satellite ET analysis | historical observation with its source-period lag; never a future forecast | `mm/day` |
| `eta_well_watered_mm` / `eta_no_irrigation_mm` | conditional ETa scenarios with named assumptions | future daily scenarios, not measurements or unconditional predictions | `mm/day` |

`eta_well_watered_mm` assumes that crop water is not limiting over the stated
scenario period. `eta_no_irrigation_mm` assumes no irrigation is applied after
the issue time; precipitation, starting condition, crop, and soil assumptions
must be recorded with the run. Neither scenario is presented as a measurement,
and neither may be relabeled as an unconditional actual-ET result.

There is intentionally no generic “actual ET forecast” layer or label. The
only future ETa-like values are the two conditional scenario layers above;
their assumptions must be visible wherever the values are shown.

## Public artifact contract

Each run produces a versioned, machine-readable receipt and a data artifact
whose records include at least:

- `schema_version`, `run_id`, `issued_at_utc`, `valid_date`, and `lead_day`;
- a stable native weather-grid cell identifier and cell geometry or reference;
- `variable`, `quantile`, `value_mm_day`, and the source issue/valid times;
- source versions, observed-date lag for `eta_analysis_mm`, and all scenario
  assumptions; and
- input checksums and the software revision that produced the artifact.

For `eto_mm`, `potential_et_c_mm`, and each conditional scenario, `quantile`
must distinguish `p10`, `p50`, and `p90`. `eta_analysis_mm` records the
observed value and observation date rather than pretending that a delayed
analysis is a forecast quantile.

The contract is intentionally independent of Helios or Irrigant runtime
integration. A later adapter may consume this documented artifact, but this
repository does not write to proprietary systems or assume their availability.

### Promotion and fixture gate

The root of `outlook.json` is the sole serving contract. It contains
`fixture_non_scientific`, `production_status`, `promotion_status`, and
`validation_status`. An adapter must reject a run whenever it is a fixture,
not promoted, or not validated; it must not infer eligibility from a sibling
`summary.json` or `validation.json`. The present direct-JSONL build path always
publishes `true`, `non_production_fixture`, `not_promoted`, and
`not_validated`, respectively.

### Immutable publication

A builder writes and fsyncs a private artifact directory before publishing the
stable `run_id` as an exclusively-created relative symlink. The exclusive
creation fails rather than replaces any existing filesystem entry at that run
id, including an empty directory created by another publisher. This procedure
assumes the output root is on a single local POSIX filesystem with atomic
exclusive `symlink(2)` creation and durable directory `fsync`; network or
object-store paths are not supported publication targets.

The stable symlink is a discovery handle, not a completed artifact path.
Consumers must use `resolve_published_run` before reading it. The resolver
rejects symlinked output ancestors, absolute or escaping targets, dangling or
non-directory generations, links or subdirectories inside a generation, an
inconsistent manifest run ID, and every recorded artifact whose SHA-256 does
not match its receipt. A parent-directory durability failure rolls back only
the link still owned by that publisher and removes its private generation, so
the run ID remains retryable without clobbering a concurrent publisher.

## Inputs and provenance

The machine-readable registry is
[`data/outlook/source_registry.json`](../../data/outlook/source_registry.json).
It identifies the minimum required variables, licenses, and latency language
for the forecast weather, observed ETa, and crop-classification sources. Raw
downloads, credentials, and generated outlooks are excluded from version
control. Reproducible runs instead record source versions, acquisition commands,
checksums, and source timestamps in a run receipt.

The operational inputs are distinct from the archived public sources used by
Phase 2. See the [data card](../data/DATA_CARD.md) for that distinction.

## Claim boundary

The public product may describe its geographic extent, weather-grid resolution,
issue time, source provenance, and uncertainty. It may describe a hindcast as
validated only after the preregistered gate in
[the outlook preregistration](../evaluation/OUTLOOK_PREREGISTRATION.md) passes.
Until then, it is an implementation or research artifact—not evidence of
forecast skill. Phase 2's OpenET result is evidence about retrospective
daily-ET prediction only; it is not validation of this 20-day outlook.
