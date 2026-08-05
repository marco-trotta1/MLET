# MLET Manuscript Technical Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to execute this plan one task at a time.

**Goal:** Correct every technical inconsistency found in the MLET manuscript audit, rebuild the affected real-data evidence, and produce a verified arXiv PDF.

**Architecture:** Treat code, frozen protocols, evidence receipts, generated claims, figures, and manuscript prose as one ordered provenance chain. Correct behavior first with failing tests. Rebuild every downstream artifact from the corrected committed code. Revise the manuscript only after the corrected result values exist.

**Tech stack:** Python 3, pytest, NumPy, JSON evidence archives, LaTeX, Tectonic, and repository verification scripts.

## Global constraints

1. Preserve the current front-page author geometry and the repaired Figure 2 arrows.
2. Use only the repository code and the local verified evidence sources.
3. Do not download replacement scientific data.
4. Keep the feasibility evaluation limited to the existing BOII case.
5. Use the target grid cell for spatial blocking. Do not use the station location.
6. Use the full SHA-256 digest for the fold calculation.
7. Describe GEFSv12 data as a retrospective reforecast. Do not claim operational issue-time availability.
8. Treat the station climatology as a fixed prior-station-history benchmark. Fold exclusion applies to learned or tuned components.
9. Use ASD-STE100 Simplified Technical English in new prose. Do not use an em dash.
10. Stage only the files owned by the current task. Do not stage unrelated user changes.
11. Run the narrow failing test first. Run the full suite before each task commit.
12. Baseline on commit `2b6c9b04dffd9f319bb7dbc69a5a7ee14b914d52`: 681 tests passed in 9.04 seconds. One pre-existing NumPy binary-size warning occurred in `tests/test_cli_phase2.py::test_qc_gridmet_prints_mean_absolute_delta`.

---

## Task 1: Correct the GEFS wind measurement height

**Files:**

- Modify: `src/mlet/outlook/eto.py`
- Modify: `src/mlet/reference/priestley_taylor.py`
- Modify: `tests/test_outlook_eto.py`
- Modify: `tests/test_reference_priestley_taylor.py`
- Modify: `tests/test_cli_qc_eto.py`
- Modify: `docs/data/GEFS_DAILY_ARTIFACT.md`

### Step 1: Write failing tests

Change the ASCE reference ETo test to require `wndht=10.0`. Add or retain a literal weather-member regression that proves the corrected ETo is approximately `6.715821947631285 mm/day`. Update the Priestley-Taylor diagnostic regression only after the test fails for the old height assumption.

### Step 2: Run the red tests

Run:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_outlook_eto.py tests/test_reference_priestley_taylor.py
```

Expected result: at least one assertion fails because the implementation passes `wndht=2.0`.

### Step 3: Implement the minimum correction

Pass `wndht=10.0` to `pyfao56.refet.ascedaily` in both code paths. Do not alter the decoded daily wind artifact. It already stores the 10 m vector magnitude from `u10` and `v10`.

Document that the ETo routine performs the standard internal 10 m to 2 m wind adjustment.

### Step 4: Run focused and full verification

Run:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_outlook_eto.py tests/test_reference_priestley_taylor.py tests/test_cli_qc_eto.py tests/test_sources_gefs_reforecast.py tests/test_eto_build.py
python3 -m pytest -q
```

Expected result: all tests pass. The only accepted warning is the recorded baseline warning.

### Step 5: Commit

Commit only the six task files with this subject:

```text
fix(eto): use the GEFS 10 m wind height
```

---

## Task 2: Derive spatial folds from target grid cells

**Files:**

- Create: `src/mlet/outlook/spatial.py`
- Create: `tests/test_outlook_spatial.py`
- Modify: `scripts/build_eto_gefs_index.py`
- Modify: `scripts/build_eto_target_index.py`
- Modify: `src/mlet/outlook/eto_hindcast.py`
- Modify: `tests/test_build_eto_gefs_index.py`
- Modify: `tests/test_build_eto_target_index.py`
- Modify: `tests/test_eto_hindcast.py`
- Modify: `tests/test_eto_archive.py`

### Step 1: Write failing spatial tests

Add tests for these invariants:

- `43.50:-116.00` maps to the one-degree block `43:-116`.
- The fold is `int(sha256(block).hexdigest(), 16) % 5`.
- The BOII target grid cell maps to fold 2.
- The station coordinates do not control the fold.
- A supplied fold that conflicts with the derived fold is rejected.

Update the existing BOII expected case identifier to `issue-20190703-station-BOII-season-JJA-fold-2`.

### Step 2: Run the red tests

Run:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_outlook_spatial.py tests/test_build_eto_gefs_index.py tests/test_build_eto_target_index.py tests/test_eto_hindcast.py tests/test_eto_archive.py
```

Expected result: the old station-coordinate and digest-prefix behavior fails.

### Step 3: Add one shared implementation

Create total functions that parse the canonical `grid_id`, derive the one-degree block, and derive the fold. Reject malformed grid identifiers at the boundary. Use the shared functions in both index builders and in hindcast validation. Remove duplicate fold calculations.

### Step 4: Run focused and full verification

Run:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_outlook_spatial.py tests/test_build_eto_gefs_index.py tests/test_build_eto_target_index.py tests/test_eto_hindcast.py tests/test_eto_archive.py
python3 -m pytest -q
```

Expected result: all tests pass. The only accepted warning is the recorded baseline warning.

### Step 5: Commit

Commit only the task files with this subject:

```text
fix(outlook): derive folds from the target grid
```

---

## Task 3: Correct reforecast timing and baseline semantics

**Files:**

- Modify: `scripts/build_eto_gefs_index.py`
- Modify: `scripts/build_eto_target_index.py`
- Modify: `src/mlet/outlook/archive.py`
- Modify: `src/mlet/outlook/eto_archive.py`
- Modify: `src/mlet/outlook/eto_hindcast.py`
- Modify: `tests/test_build_eto_gefs_index.py`
- Modify: `tests/test_build_eto_target_index.py`
- Modify: `tests/test_outlook_archive.py`
- Modify: `tests/test_eto_archive.py`
- Modify: `tests/test_eto_hindcast.py`
- Modify: `docs/evaluation/OUTLOOK_PREREGISTRATION.md`
- Modify: `docs/data/GEFS_DAILY_ARTIFACT.md`

### Step 1: Write failing timing tests

Add tests that require GEFS index schema version 2 and source timing with these fields:

```json
{
  "temporal_role": "retrospective_reforecast",
  "source_issue_at": "2019-07-03T00:00:00Z",
  "archive_available_at": "2026-08-04T18:08:54.243122Z"
}
```

Require the archive availability time to equal the verified source retrieval time. Require the source issue time to equal the candidate issue. Reject a false `available_at` value that predates archive availability. Keep the AgriMet index schema at version 1.

Add a baseline regression that uses all strictly prior station years for the matching day of year. Prove that the evaluated year is absent. Do not remove the station because its grid fold is held out.

### Step 2: Run the red tests

Run:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_build_eto_gefs_index.py tests/test_build_eto_target_index.py tests/test_outlook_archive.py tests/test_eto_archive.py tests/test_eto_hindcast.py
```

Expected result: the schema version, false issue-time availability, and old baseline wording or behavior fail.

### Step 3: Implement explicit timing records

Parse GEFS index schema version 2 into a typed timing record. Keep the AgriMet schema version 1 path explicit. Emit source-receipt schema version 2 with `temporal_role`, `source_issue_at`, and `archive_available_at`. Set the outer evidence provenance availability to the latest real source or target availability. Do not represent the retrospective archive as operationally available at the historical issue time.

Keep the climatology calculation station-specific and day-of-year-specific. Use every strictly prior year. Apply fold exclusion only to learned or tuned components.

### Step 4: Update the protocol

Replace contradictory timing and climatology statements. State that the BOII result is a retrospective reforecast diagnostic. State that the fixed climatology uses prior station history and does not train across spatial folds.

### Step 5: Run focused and full verification

Run:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_build_eto_gefs_index.py tests/test_build_eto_target_index.py tests/test_outlook_archive.py tests/test_eto_archive.py tests/test_eto_hindcast.py
python3 -m pytest -q
```

Expected result: all tests pass. The only accepted warning is the recorded baseline warning.

### Step 6: Commit

Commit only the task files with this subject:

```text
fix(outlook): record retrospective source timing
```

---

## Task 4: Make the generation pipeline enforce exact scope and claims

**Files:**

- Modify: `scripts/build_arxiv_claims.py`
- Modify: `scripts/build_arxiv_figures.py`
- Modify: `scripts/verify_arxiv_manuscript.py`
- Modify: `scripts/build_eto_gefs_index.py`
- Modify: `tests/test_build_eto_gefs_index.py`
- Create: `tests/test_build_arxiv_claims.py`
- Create: `tests/test_build_arxiv_figures.py`
- Create: `tests/test_verify_arxiv_manuscript.py`

### Step 1: Write failing generator tests

Add focused tests for these rules:

- M2 is the lowest-MAE model only among B1, B2, and M1 through M3 on the common 7,923-row sample.
- B0 is reported separately because it uses 1,555 consecutive-day pairs.
- H2 is a preregistered comparison or hypothesis. It is not a model.
- The p10 to p90 interval is an uncalibrated ensemble quantile band.
- The value 0.80 is the nominal coverage target. The measured value is empirical coverage. Neither value is interval width.
- The grid label is `common 0.5-degree GEFS grid-point subset`.
- The Phase 2 label is `station-held-out 10-fold evaluation`.
- The verifier rejects every retired phrase listed above.
- A repeatable `--station-id` option restricts index generation to named mapped stations.
- An unknown selected station fails before index generation.
- Figure case paths come from the one-case evidence record. No fold identifier is hard-coded.
- The support-tensor annotation derives its season, fold, and count from evaluated metrics.
- The GEFS index receipt names the stream-index artifact next to its SHA-256 digest.

### Step 2: Run the red tests

Run:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_build_arxiv_claims.py tests/test_build_arxiv_figures.py tests/test_verify_arxiv_manuscript.py tests/test_build_eto_gefs_index.py
```

Expected result: at least one assertion fails against the current scripts.

### Step 3: Implement exact generation rules

Validate the common-sample M2 comparison against B1, B2, M1, M2, and M3. Keep B0 outside that comparison. Update labels, legends, annotations, and verifier phrases. Label measured coverage as empirical coverage and record 0.80 separately as the nominal target. Derive the feasibility case paths and support annotation from the evidence record. Bind the stream-index path and digest in its receipt. Do not hard-code scientific values or fold identifiers that can be read from machine records.

Add a repeatable `--station-id` option to the GEFS index builder. Keep the default behavior unchanged. Validate requested identifiers against the mapping before generation. Use this option to make the one-station feasibility scope reproducible.

### Step 4: Run focused and full verification

Run:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_build_arxiv_claims.py tests/test_build_arxiv_figures.py tests/test_verify_arxiv_manuscript.py tests/test_build_eto_gefs_index.py
```

Then run:

```bash
python3 -m pytest -q
```

Expected result: all tests pass. The only accepted warning is the recorded baseline warning.

### Step 5: Commit

Commit only the generator and index scripts and their tests with this subject:

```text
fix(manuscript): enforce exact generation scope
```

---

## Task 5: Rebuild the real BOII evidence and manuscript inputs

**Files:**

- Modify: `data/outlook/gefs_reforecast_20190703_candidate/manifest.json`
- Modify: `data/outlook/gefs_reforecast_20190703_candidate/outlook.json`
- Modify: `data/outlook/gefs_reforecast_20190703_manifest.json`
- Modify: `data/outlook/gefs_reforecast_20190703_outlook.json`
- Modify: `data/outlook/gefs_reforecast_20190703_artifact_receipt.json`
- Modify: `data/outlook/gefs_reforecast_20190703_feasibility.json`
- Modify: `data/outlook/eto_feasibility_gefs_index.json`
- Create: `data/outlook/gefs_reforecast_20190703_stream_index.json`
- Modify: `data/outlook/eto_feasibility_gefs_index-receipt.json`
- Modify: `data/outlook/eto_feasibility_agrimet_index.json`
- Replace the fold-4 files under `data/outlook/eto_feasibility_targets/` and `data/outlook/eto_feasibility_archive/` with fold-2 files.
- Modify: `manuscript/arxiv/generated_claims.tex`
- Modify generated figure files under `manuscript/arxiv/figures/`

### Step 1: Record inputs before generation

Use these verified local inputs:

- `MLET Evidence/gefs-v12-20190703/gefs-20190703.pointer`
- `MLET Evidence/agrimet-historical/agrimet-historical-rows-v2.json`
- `MLET Evidence/agrimet-historical/agrimet-historical-exclusions-v2.json`
- `MLET Evidence/agrimet-historical/derived/agrimet-historical-gefs-mapping.json`

Record the current committed code SHA. Use the existing source retrieval time `2026-08-04T18:08:54.243122Z`.

### Step 2: Build into new temporary directories

Use `mktemp -d`. Do not overwrite the checked-in evidence until every staged output verifies. Build the ETo candidate from the local pointer. Build a GEFS index restricted to BOII. Build the corresponding target index and target. Assemble the archive. Run the ETo hindcast. Confirm that the only case is `issue-20190703-station-BOII-season-JJA-fold-2`.

Use the tested `--station-id BOII` option. Do not create a hand-edited index.

### Step 3: Verify staged evidence before replacement

Check every recorded SHA-256 digest. Run the narrow archive and hindcast tests against the staged output. Confirm that the wind-corrected result values differ from the old result values for the expected physical reason.

### Step 4: Replace only exact generated files

Copy the verified staged files over the listed tracked files. Remove the exact tracked fold-4 case paths with `git rm`. Add the fold-2 case paths. Update duplicate top-level candidate files and all receipts that bind candidate hashes or run identifiers.

Regenerate:

```bash
PYTHONPATH=src python3 scripts/build_arxiv_claims.py --out manuscript/arxiv/generated_claims.tex
PYTHONPATH=src python3 scripts/build_arxiv_figures.py --out manuscript/arxiv/figures
```

Run both commands without a process-local override or monkeypatch.

### Step 5: Run evidence and full verification

Run the focused archive, hindcast, claim, and figure tests. Then run:

```bash
python3 -m pytest -q
```

Expected result: all tests pass. The only accepted warning is the recorded baseline warning.

### Step 6: Commit

Commit only the rebuilt evidence, generated claims, generated figures, and any tested BOII selector with this subject:

```text
data(outlook): rebuild the BOII reforecast evidence
```

---

## Task 6: Revise and verify the arXiv manuscript

**Files:**

- Modify: `manuscript/arxiv/mlet_preprint.tex`
- Modify: `manuscript/arxiv/ARXIV_SUBMISSION.md`
- Modify: `manuscript/manuscript.md`
- Modify: `manuscript/DATA_AVAILABILITY.md`
- Modify: `README.md` only where its manuscript terminology is stale.
- Modify: `scripts/verify_arxiv_manuscript.py`
- Modify: `tests/test_verify_arxiv_manuscript.py`
- Modify: `output/pdf/mlet_preprint.pdf`
- Replace: `output/arxiv/mlet_preprint_source/`
- Modify: `output/arxiv/mlet_preprint_source.tar.gz`

### Step 1: Add manuscript-verifier failures

Extend the verifier tests before prose edits. Require the final manuscript to define each of these items at first use: MLET, GEFSv12, NOAA, USBR, ASCE-EWRI, ETos, ETo, MAE, RMSE, SHA-256, UTC, 00Z, H2, BOII, DJF, MAM, JJA, and SON.

Require these additional facts:

- The visible title and PDF metadata state `Incremental Predictive Value of OpenET`.
- B1 uses a static pooled training-set ETo ratio. It is not crop-specific.
- Phase 2 benchmark ETo is gridMET ETo.
- Outlook ETo is GEFS-derived ASCE standardized short-reference ETo.
- The p10 to p90 band is uncalibrated.
- AgriMet ETos is a published station-derived target. It is not a direct flux measurement.
- The BOII case is retrospective.
- The implementation map includes the decoder script, batch decoder, GRIB parser, daily artifact builder, and ETo routine.
- The orphan water-balance limitation is absent.

Run the verifier test and confirm that the current manuscript fails.

### Step 2: Revise technical prose and equations

Make these surgical corrections:

1. Define every acronym at first use. Define `frozen`, `promotion`, `validation complete`, `skillful`, and `release review` where the governance terms first appear.
2. Define the Phase 2 response, gridMET benchmark ETo, OpenET input, residuals, standardized covariates, intercept handling, and the B1 positive-ETo rule.
3. Define all ASCE equation symbols and units: air temperature, net radiation, soil heat flux, vapor-pressure slope, psychrometric constant, 2 m wind, saturation vapor pressure, and actual vapor pressure.
4. Define the empirical ensemble quantile convention.
5. Replace `field-withheld` with `station-held-out 10-fold evaluation`.
6. Define the H2 rule as at least 10% lower pooled MAE than the better of B1 and B2, with a station-blocked 95% confidence interval that excludes zero.
7. State that M2 has the lowest MAE only within the common-sample fitted comparison. Keep B0 separate.
8. Replace `calibrated interval` with `uncalibrated ensemble quantile band`.
9. State nominal coverage and mean band width as separate quantities.
10. Replace `native grid` with `common 0.5-degree GEFS grid-point subset`.
11. Replace `weather-derived demand index` with `standardized reference evapotranspiration rate`.
12. Describe AgriMet ETos as a published station-derived target.
13. Describe the climatology as prior-years station history.
14. Describe the BOII result as a retrospective reforecast diagnostic.
15. Replace the ambiguous signed improvement sentence with a baseline-minus-forecast MAE difference and its direction.
16. Remove the non-serving FAO-56 water-balance scaffold limitation.
17. Correct the implementation map for the complete GEFS decode and ETo chain.

Use APA author-year in-text citations. Format every inline bibliography entry in APA style. Confirm that every bibliography entry is cited and every citation has one bibliography entry. Add no unsupported claim.

### Step 3: Compile and verify

Run:

```bash
PYTHONPATH=src python3 scripts/build_arxiv_claims.py --out manuscript/arxiv/generated_claims.tex
PYTHONPATH=src python3 scripts/build_arxiv_figures.py --out manuscript/arxiv/figures
(cd manuscript/arxiv && tectonic --outdir ../../output/pdf --keep-logs mlet_preprint.tex)
PYTHONPATH=src python3 scripts/verify_arxiv_manuscript.py --pdf output/pdf/mlet_preprint.pdf
python3 -m pytest -q
```

Expected result: the manuscript verifier succeeds, the full suite succeeds, and the only accepted warning is the recorded baseline warning.

### Step 4: Inspect the rendered PDF

Render all PDF pages to images. Inspect every page. Pay special attention to these items:

- The author block remains geometrically centered and evenly spaced.
- The Figure 2 red and gray arrows remain continuous.
- No caption, equation, table, citation, or plot label overlaps another element.
- Page 5 has balanced graph spacing.
- The reference list is complete and readable.

If a visual defect appears, fix the source, compile again, and inspect the affected pages again.

### Step 5: Sync the arXiv source bundle

Rebuild `output/arxiv/mlet_preprint_source/` from the verified source. Rebuild `output/arxiv/mlet_preprint_source.tar.gz`. Verify that a clean extraction compiles to the same manuscript content.

### Step 6: Commit

Commit only the manuscript source, documentation, verified PDF, and source bundle with this subject:

```text
docs(manuscript): correct technical terminology
```

---

## Final review and completion gate

1. Give each task commit to a fresh specification reviewer.
2. Resolve every Critical or Important review finding before the next task.
3. Give the complete base-to-head diff to a fresh broad reviewer.
4. Run the full suite after all review fixes.
5. Rebuild the claims, figures, PDF, verifier output, and source tarball after the final code change.
6. Reinspect every PDF page after the final build.
7. Report the exact test count, warning count, manuscript verifier result, PDF page count, and remaining limitations.
