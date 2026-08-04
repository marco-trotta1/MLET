# MLET Manuscript-Ready Finish Specification

**Date:** 2026-07-29
**Status:** Non-gated implementation completed on 2026-07-31; scientific outcome gates remain open
**Primary objective:** Finish the remaining MLET product work required to write the manuscript end to end, without allowing UI work, conditional ET projections, or Irrigant integration to expand the scientific scope.

## 1. Decisions frozen by this specification

1. **Formal validation scope:** only the 20-day `eto_mm` forecast is a formal hindcast target.
2. **Other layers:** `potential_et_c_mm`, `eta_well_watered_mm`, and `eta_no_irrigation_mm` remain conditional, independently unvalidated projections. `eta_analysis_mm` remains a delayed historical analysis.
3. **Meaning of validation:** “validation complete” means that MLET was evaluated under the frozen, issue-time-valid protocol. Completion does not depend on passing an arbitrary performance threshold. A manuscript claim of “skillful” is allowed only where the paired confidence interval supports it.
4. **Primary comparator:** station-specific day-of-year ETo climatology estimated without using the evaluated year/fold. Persistence may be reported as a secondary comparator.
5. **Manuscript boundary:** OpenET acquisition keys, CDL acquisition, soil-moisture assimilation, hybrid/LSTM training, ETa forecast validation, UI redesign, operational promotion, and Irrigant integration are not manuscript-readiness gates.

## 2. Assumptions to verify before implementation

- NOAA GEFS version 12 reforecasts provide the required archived meteorological fields through lead day 20 for a reproducible 2013–2019 overlap.
- USBR AgriMet exposes sufficient historical daily ASCE standardized short-reference ETo (`ETos`) for Idaho stations during that overlap.
- Published AgriMet ETos can serve as the independent target. MLET must not recompute the target with the same code path used for its forecast.
- A station can be mapped deterministically to one MLET grid cell while retaining a distinct station `target_id`.
- The target journal and manuscript markup format are not yet selected, so the repository will generate publication-neutral Markdown, BibTeX, CSV, JSON, and SVG artifacts.

If the first GEFS/AgriMet feasibility case fails, stop bulk acquisition and document the exact missing field, date range, or licensing/provenance problem. Do not silently substitute gridMET, OpenET, operational GEFS, or a recomputed target.

## 3. Definition of done

Feature development is complete when all of the following are true:

1. A dated, pre-outcome amendment freezes ETo-only validation, baselines, metrics, support rules, and claim language.
2. A real, checksum-bound GEFS reforecast and independent AgriMet target archive can be rebuilt and verified from public sources.
3. The ETo-only hindcast covers leads 1–20, all four seasons, and all five spatial folds, and emits complete metrics regardless of whether performance is favorable.
4. Phase 2 and ETo result tables/figures regenerate deterministically from machine-readable result records.
5. A clean-clone verification command passes, and the manuscript skeleton can be written without another model, data-source, product, or integration feature.

The UI may still be unattractive. Irrigant may still be unavailable. Neither condition reopens MLET feature development.

## 4. Phase 0 — Freeze the scientific and product contracts

**Estimate:** 2–4 working days
**Gate:** must merge before downloading the bulk hindcast outcome archive.

### 4.1 Protocol amendment

Update:

- `docs/evaluation/OUTLOOK_PREREGISTRATION.md`
- `docs/outlook/PRODUCT_CONTRACT.md`
- `docs/data/DATA_CARD.md`
- `docs/REPRODUCIBILITY.md`
- `README.md`

Add a dated amendment rather than silently rewriting the earlier frozen protocol. Freeze:

- formal target: `eto_mm` only;
- leads: 1–20 daily;
- primary target: published AgriMet ASCE short-reference ETos;
- primary baseline: leakage-safe station/day-of-year climatology;
- metrics: p50 MAE, RMSE, bias; p10/p50/p90 mean pinball loss; p10–p90 coverage and width;
- stratification: lead, season, and five spatial folds;
- uncertainty: paired bootstrap confidence intervals clustered by issue date and station;
- support rule: at least 30 paired station-date targets in every reported lead × season × fold cell;
- missing-support rule: report the cell and mark the evaluation incomplete; never impute targets;
- coverage reference: nominal 0.80, reported with uncertainty but not used as a pass/fail completion threshold;
- skill language: “skillful” only when the relevant paired 95% confidence interval for improvement over climatology excludes zero;
- completion language: an unfavorable result is still a completed evaluation and a manuscript result.

### 4.2 Evidence and status schemas

Create an explicitly ETo-only evidence bundle schema version 4 and target schema version 2. Do not reinterpret or weaken the existing full-product v3 schema. Existing v3 fixtures may remain readable through their explicitly legacy/scenario path, but they cannot produce the manuscript's ETo evaluation receipt.

Required validation scope:

```json
{
  "formal_hindcast_layers": ["eto_mm"],
  "unvalidated_projection_layers": [
    "potential_et_c_mm",
    "eta_well_watered_mm",
    "eta_no_irrigation_mm"
  ],
  "nonforecast_analysis_layers": ["eta_analysis_mm"]
}
```

Use one pre-evaluation candidate vocabulary everywhere:

```json
{
  "fixture_non_scientific": false,
  "production_status": "research_candidate",
  "promotion_status": "not_promoted",
  "validation_status": "evaluation_pending"
}
```

Local MLET output must never mutate itself to `validated`. The evaluator produces a digest-bound evaluation receipt; a separate authority may later issue an operational release receipt. Operational promotion is not a manuscript gate.

### 4.3 Code changes

Change:

- `src/mlet/outlook/hindcast.py`
- `src/mlet/outlook/serve_contract.py`
- `src/mlet/outlook/publish.py`
- `src/mlet/outlook/manifest.py`
- `src/mlet/experiments/idaho_outlook_residual.py`

Required behavior:

- Add a schema-v4 ETo branch with `VALIDATION_LAYERS = ("eto_mm",)`; retain v3's three-layer semantics only for explicitly legacy full-scenario evidence.
- Reject ETc, ETa analysis, and both ETa scenarios as formal `HindcastRow` targets.
- Remove scenario receipts from required ETo evidence.
- Require ETo quantiles and targets at leads 1–20.
- Add `target_id` for station identity while retaining mapped `grid_id`.
- Recompute and verify the spatial fold from frozen station/grid coordinates; do not trust a caller-supplied fold.
- Add mean pinball loss, support counts, baseline deltas, and paired confidence intervals to the evaluation result.
- Remove the circular requirement that an input candidate already be validated.
- Bind the exact validation scope into evaluation and authority-request digests.
- Propagate layer-level `validation_role` through serving, GeoJSON, summary, and candidate artifacts.
- Preserve `promotion: false` and all existing fail-closed fixture behavior.
- Prevent the residual-model experiment from inheriting an ETo validation claim.

### 4.4 Tests first

Change:

- `tests/test_outlook_hindcast.py`
- `tests/test_outlook_build.py`
- `tests/test_outlook_publish.py`
- `tests/test_outlook_manifest.py`
- `tests/test_outlook_residual_model.py`
- `tests/test_build_site.py`

Add tests that prove:

- v3 evidence cannot be reinterpreted as v4 ETo evidence or produce the manuscript receipt;
- ETo-only evidence can be complete without scenario receipts;
- ETc/ETa rows cannot change ETo metrics or eligibility;
- every ETo lead is required;
- the fold is derived from coordinates and detects tampering;
- mean pinball loss and baseline deltas match hand-calculated fixtures;
- missing support blocks “evaluation complete” but poor skill does not;
- no root status can imply validation of conditional layers;
- all published representations preserve the same layer-level claim boundary.

### 4.5 Examples and stale documentation

- Add separate `examples/outlook/eto_hindcast_evidence.json` and `examples/outlook/residual_model_evidence.json`; retain the old file only as a legacy full-product fixture.
- Mark `docs/superpowers/plans/2026-07-16-idaho-regional-et-outlook.md` as superseded for validation scope without rewriting its history.
- Mark `docs/evaluation/2026-07-28-HYBRID_VS_LSTM_PROTOCOL.md` and `docs/evaluation/OUTLOOK_RESIDUAL_MODEL_PROTOCOL.md` as deferred, non-gating research.
- Update `MLET_ML_DECISION_MAP.md` so completed or deferred work is not presented as active manuscript scope.

### 4.6 Verification

```bash
pytest -q tests/test_outlook_hindcast.py tests/test_outlook_build.py tests/test_outlook_publish.py tests/test_outlook_manifest.py tests/test_outlook_residual_model.py tests/test_build_site.py
```

Expected result: all contract tests pass; no real outcome data have been evaluated.

## 5. Phase 1 — Build and verify the real hindcast sources

**Estimate:** 5–9 working days plus download time
**Gate:** one complete issue/station feasibility case before bulk acquisition.

### 5.1 GEFS reforecast adapter

Prefer a pinned external GRIB-to-tabular transform feeding the existing strict importer rather than adding a large GRIB stack to MLET core.

Change or add:

- `scripts/decode_gefs_reforecast.py`
- `src/mlet/sources/gefs.py`
- `tests/test_sources_gefs.py`
- `docs/data/GEFS_DAILY_ARTIFACT.md`
- `data/outlook/source_registry.json`

Requirements:

- pin the NOAA collection, cycle, ensemble membership, variables, units, accumulation semantics, grid, and decoder versions;
- record source URI, retrieval time, `available_at`, ETag/version where available, raw checksum, normalized checksum, and transform version;
- normalize all required inputs for the existing ASCE ETo calculation;
- reject missing members, duplicate keys, nonmonotonic leads, unit ambiguity, and data unavailable at issue time;
- demonstrate one archived issue through lead 20 before bulk acquisition.

Proposed archive window: weekly 00Z GEFSv12 reforecast issues from 2013-01-01 through 2019-12-31, using every available ensemble member for the selected weekly cycle. Freeze the exact cadence after the feasibility case confirms NOAA archive structure; do not cherry-pick dates by forecast performance.

### 5.2 AgriMet ETo target adapter

Add:

- `src/mlet/sources/agrimet.py`
- `tests/test_sources_agrimet.py`
- `docs/data/AGRIMET_ETO_ARTIFACT.md`
- `data/outlook/agrimet_station_registry.json`

Required target row:

```json
{
  "target_id": "USBR_AGRIMET_STATION_ID",
  "grid_id": "MLET_GRID_ID",
  "valid_date": "YYYY-MM-DD",
  "target_mm": 4.5,
  "target_kind": "independent_asce_short_reference_eto"
}
```

Requirements:

- use published daily ETos when available;
- preserve original units and explicit millimeter conversion;
- pin station coordinates and station-history metadata;
- exclude dates before a station’s documented operation or after relocation unless the segment is separately identified;
- never fill missing observed ETos;
- retain all eligible Idaho stations and publish exclusion reasons;
- map each station to the grid deterministically and retain both identities;
- compute five spatial folds from frozen 1-degree tiles and a documented Idaho boundary source.

### 5.3 Archive assembler

Add:

- `src/mlet/outlook/archive.py`
- CLI command in `src/mlet/cli.py`
- `tests/test_outlook_archive.py`
- `docs/data/OUTLOOK_HINDCAST_ARCHIVE.md`

Public entry point:

```python
build_eto_hindcast_archive(
    gefs_index: Path,
    agrimet_index: Path,
    destination: Path,
) -> Path
```

It must create immutable issue cases, manifests, target artifacts, source receipts, holdout receipts, and a schema-v4 evidence bundle. Raw and bulky normalized data stay outside Git; registries, checksums, inclusion tables, schemas, and compact result records are committed.

### 5.4 Feasibility verification

```bash
pytest -q tests/test_sources_gefs.py tests/test_sources_agrimet.py tests/test_outlook_archive.py
mlet outlook build-eto-hindcast-archive --gefs-index ... --agrimet-index ... --destination ...
mlet outlook hindcast --evidence ... --output ...
```

Expected result for the feasibility case: one real issue, at least one independent station target, all 20 leads, immutable receipts, and an intentionally incomplete scientific evaluation because full folds/seasons are not yet present.

## 6. Phase 2 — Add the real research-candidate build path

**Estimate:** 3–5 working days

Add a narrow ETo path instead of making the existing `OutlookDay` full-product fields optional:

- `src/mlet/outlook/eto_build.py`
- `src/mlet/outlook/eto_contract.py`
- `tests/test_eto_build.py`
- `tests/test_eto_contract.py`

Change only the shared seams required in:

- `src/mlet/outlook/manifest.py`
- `src/mlet/outlook/serve_contract.py`
- `src/mlet/outlook/publish.py`
- `src/mlet/cli.py`
- their focused manifest, serving, publish, and CLI tests

Required behavior:

- accept only manifest-backed, checksum-verified nonfixture GEFS artifacts;
- build `eto_mm` p10/p50/p90 for every grid and lead;
- emit an ETo-only research artifact; do not weaken or relabel the existing full-product artifact;
- emit immutable `research_candidate` artifacts with `evaluation_pending`;
- never require OpenET, CDL, crop, soil, or irrigation inputs to build the ETo manuscript candidate;
- continue requiring those inputs under the existing full-product/scenario path;
- keep the fixture path visibly non-scientific and incompatible with the real evidence gate.

Verification:

```bash
pytest -q tests/test_eto_build.py tests/test_eto_contract.py tests/test_outlook_manifest.py tests/test_outlook_publish.py tests/test_cli.py
```

Expected result: a real ETo-only candidate can be built without an OpenET key, while full conditional-map requests still fail closed when their inputs are absent.

## 7. Phase 3 — Run the frozen full ETo hindcast

**Estimate:** 4–8 working days plus acquisition/runtime

### 7.1 Full evidence run

- Acquire the entire frozen 2013–2019 weekly overlap.
- Build all eligible forecast issues before examining performance.
- Evaluate leads 1–20 for every eligible station target.
- Require all four seasons and all five spatial folds.
- Emit explicit exclusions and missing-support cells.
- Do not revise the protocol because of observed skill.

### 7.2 Required outputs

Generate:

- `docs/results/idaho_eto_hindcast.json`
- `docs/results/idaho_eto_hindcast.md`
- `docs/results/tables/eto_skill_by_lead.csv`
- `docs/results/tables/eto_skill_by_season.csv`
- `docs/results/tables/eto_skill_by_spatial_fold.csv`
- `docs/results/figures/eto_error_by_lead.svg`
- `docs/results/figures/eto_coverage_by_lead.svg`
- `docs/results/figures/eto_bias_by_season.svg`

The machine-readable result must contain archive/evaluation digests, revision, source versions, station and row counts, exclusions, support, baseline metrics, model metrics, paired deltas, confidence intervals, and claim-safe generated prose.

### 7.3 Scientific outcome rules

- If the evaluation is complete and skill is favorable, report where the paired 95% CI supports improvement.
- If it is complete and skill is neutral or unfavorable, report that result and proceed to manuscript writing.
- If required support or provenance is incomplete, repair the data/archive defect without changing the model or protocol.
- Model changes after inspecting full results create a new preregistered experiment; they are not part of this finish specification.

## 8. Phase 4 — Freeze manuscript artifacts and stop building

**Estimate:** 3–5 working days

### 8.1 Harden the existing Phase 2 result

Add machine-readable provenance beside `docs/results/phase2_openet_value.md`:

- `docs/results/phase2_openet_value.json`
- `docs/results/tables/phase2_model_comparison.csv`
- `docs/results/figures/phase2_model_comparison.svg`

Record the existing result with its exact seed, split, manifest digest, software revision, 85 stations, 7,923 common-complete rows, bootstrap settings, 43.4% MAE reduction, 0.658 mm/day paired delta, and 95% CI 0.399–0.911.

### 8.2 Deterministic artifact generator

Add:

- `scripts/build_manuscript_artifacts.py`
- `tests/test_manuscript_artifacts.py`

The script consumes only hash-bound result JSON and deterministically generates all committed CSV, Markdown, and SVG outputs. It must not depend on notebook state, network access, current time, or unseeded randomness.

### 8.3 Manuscript source skeleton

Add:

- `manuscript/manuscript.md`
- `manuscript/references.bib`
- `manuscript/SUPPLEMENT.md`
- `manuscript/DATA_AVAILABILITY.md`
- `manuscript/CODE_AVAILABILITY.md`
- `manuscript/LIMITATIONS.md`

Populate headings, claim boundaries, artifact links, method placeholders, and bibliography entries. Do not fabricate prose for results that have not yet been generated.

### 8.4 One finish command

Extend `scripts/verify.sh` or add `scripts/verify_manuscript_ready.sh` to run:

- the full test suite;
- serving-path isolation checks;
- evidence/result schema validation;
- deterministic manuscript artifact regeneration and byte comparison;
- broken-link/reference checks;
- manuscript build or render smoke test.

Update all living documentation to point to this single command.

### 8.5 Final stop record

Add a dated feature-freeze note stating:

- Phase 2 and ETo evaluation are the manuscript’s completed evidence;
- ETc/ETa are conditional projections only;
- hybrid/LSTM, assimilation, ETa validation, UI redesign, operational promotion, and irrigation-decision modeling are future work;
- future experiments cannot retroactively alter the frozen manuscript results.

## 9. Irrigant boundary after manuscript readiness

The only MLET-side work permitted before access to Irrigant is a contract and conformance fixture. It is optional for manuscript readiness.

The later Irrigant adapter must:

- consume descriptor-verified, checksum-bound artifacts;
- accept ETo only under a trusted layer-specific receipt;
- preserve conditional labels for ETc/ETa;
- refuse fixtures and unknown schema versions;
- never pass regional ETc/ETa projections directly into irrigation recommendations;
- display: “Regional outlook — not a field-level irrigation recommendation.”

No speculative Irrigant code should be added to this repository without its actual API or repository.

## 10. Explicitly not required before manuscript writing

- OpenET API keys or a new OpenET acquisition path.
- A new CDL download/intersection pipeline.
- Soil-moisture or data-assimilation work.
- Hybrid or LSTM training.
- Validation of potential ETc or either ETa scenario.
- UI redesign.
- A production deployment or external promotion receipt.
- Direct Irrigant integration.

## 11. Effort and order

| Order | Deliverable | Estimate | Manuscript gate |
|---|---|---:|---|
| 1 | Protocol, schemas, ETo-only evaluator, tests | 2–4 days | Yes |
| 2 | GEFS + AgriMet verified archive | 5–9 days | Yes |
| 3 | Real research-candidate build | 3–5 days | Yes |
| 4 | Full ETo hindcast and result record | 4–8 days | Yes |
| 5 | Deterministic artifacts and manuscript skeleton | 3–5 days | Yes |

**Total:** approximately 17–31 working days, or 3.5–6 weeks. Download speed and public archive quirks are the largest schedule risks.

## 2026-07-31 implementation note

Completed without assuming institutional storage or compute:

- public USBR station registry snapshot and checksum receipt;
- current-only station metadata loader with a fail-closed history boundary;
- ETo-only candidate build and evidence-bundle commands;
- strict ETo candidate contract validation and paired bootstrap intervals;
- a public ETo hindcast archive assembler and CLI alias;
- deterministic Phase 2 manuscript artifact checks;
- manuscript draft, supplement, data availability, code availability, and
  limitations files; and
- a non-gated build verification command.

Still gated by external data or authority:

- complete historical station-location segments;
- the full GEFS and AgriMet outcome archive;
- the full ETo hindcast result; and
- any institutional storage or compute allocation.

## 12. Final acceptance checklist

- [ ] The protocol amendment predates the first full outcome evaluation.
- [ ] The evaluator scores only ETo and reports mean pinball loss.
- [ ] Candidate and result contracts carry layer-specific claim status.
- [ ] One real feasibility issue passes before bulk acquisition.
- [ ] The full archive has five folds, four seasons, 20 leads, and required support.
- [ ] The evaluation is complete, regardless of favorable or unfavorable skill.
- [ ] Phase 2 and ETo artifacts regenerate byte-for-byte.
- [ ] The full test and manuscript-ready verification command passes.
- [ ] All living documentation uses the same claim boundary.
- [ ] Feature development is declared frozen and manuscript writing begins.
