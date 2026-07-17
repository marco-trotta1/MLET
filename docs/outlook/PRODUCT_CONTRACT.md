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
id, including an empty directory created by another publisher. Operators must
place the output root on one local POSIX filesystem where exclusive
`symlink(2)` creation is atomic and directory `fsync` is durable. Network and
object-store paths are not supported publication targets. MLET cannot prove
those filesystem properties at runtime; they are deployment preconditions.

The stable symlink is a discovery handle, not a completed artifact path.
`build_outlook` returns only its `run_id` and output-root reference; it never
returns the private generation pathname. Consumers must call
`read_published_run` (with `resolve_published_run` retained as an alias) with
that pair and use the returned immutable artifact bytes—not a `Path`—before
serving or adapting a run. The reader samples the stable target identity,
opens and pins the matching generation descriptor before trusting its name,
then opens each member with POSIX `openat(2)`-style directory descriptors and
`O_NOFOLLOW`; it validates the manifest run ID and computes every receipt hash
from the exact pinned bytes it returns. It rejects symlinked output ancestors,
absolute or escaping targets, dangling or non-directory generations, links or
subdirectories inside a generation, an inconsistent manifest run ID, and every
recorded artifact whose SHA-256 does not match its receipt. A private
generation replacement before either builder or reader descriptor pinning is
rejected. A replacement after pinning cannot redirect the pinned descriptor.

This publication protocol also requires descriptor-relative operations,
`O_DIRECTORY`, and `O_NOFOLLOW`. MLET checks those Python/OS interfaces only
when the builder or reader is invoked and fails clearly if they are absent. It
does not claim that successful interface checks establish local-storage,
exclusive-symlink, or durable-`fsync` semantics; operators must supply those
preconditions.

### Trusted output-root threat model

The output root is a security boundary, not a general shared scratch path.
Before either a build or read, MLET traverses every existing absolute component
through non-following directory descriptors. The supported ACL-inspection
platforms are Darwin and Linux. Every component must be a directory owned by
the effective user or by root, have neither group nor other write permission,
and contain none of the observable ACL markers: `com.apple.acl.text` on
Darwin, or `system.posix_acl_access` / `system.posix_acl_default` on Linux.
Missing or failed ACL inspection—and every other platform—fails closed. This
strict policy rejects any ACL-bearing component rather than attempting to infer
whether an individual ACL entry grants write access.

Root-owned non-writable components are accepted by the implementation even
when one is the final output root. That is an ownership-trust decision, not a
promise a non-root publisher can create there; such a builder will still fail
normally for lack of filesystem permission. In normal operation the final
publisher root is effective-user owned. Group- or world-writable paths,
including sticky temporary directories, and symlinked components are rejected.
Operators must provision a trusted per-publisher root instead of attempting
publication directly in a hostile writable spool.

The ownership, mode, and ACL checks define a narrow supported trust boundary;
mode bits alone are not represented as proof that no hostile writer exists.
Within that boundary, descriptor checks fail closed for detectable corruption
such as symlink or inode substitution. Portable POSIX cannot distinguish a
perfectly identical directory substituted before its first open inside an
attacker-writable root; MLET makes no security claim for that unsupported
configuration. Readers independently verify the manifest run ID and every
recorded SHA-256 from the exact pinned bytes they return, so the stable relative
link remains discovery-only under this trusted-root model.

If the final directory `fsync` fails after an exclusive public claim,
durability is uncertain. The builder deliberately does not attempt a
readlink-then-unlink rollback, because POSIX cannot make that unlink
conditional and it could erase a replacement publisher's entry. It leaves the
claim and private generation for explicit inspection instead.

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
