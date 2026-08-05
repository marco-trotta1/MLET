# Final fix report

## Scope

The fix wave starts from base revision `fb64dab`.

The scientific input revision is `d8feb34`.

The package includes the final manuscript, generated artifacts, source archive,
and this report.

Unrelated user files and untracked evidence paths remain unchanged.

## Phase 2 evidence

The fresh independent reproduction uses the existing interim evidence directory.

The result record uses schema version 2.

It includes 85 stations and 2,000 station-blocked bootstrap replicates.

The result preserves these metrics:

- B0 uses 1,555 consecutive-day pairs.
- B1 uses 7,923 common fitted-model rows.
- B2 MAE is 1.5142371784206408 mm/day.
- M2 MAE is 0.7812075909524736 mm/day.
- M3 MAE is 0.8563053222903725 mm/day.
- H2 delta is 0.6579318561302683 mm/day.
- H2 reduction is 0.43449722771732197.
- The 95 percent interval is [0.39940040090677065, 0.9114997667489539] mm/day.

The result provenance stores seed `20260713` and revision `d8feb34`.

The result digest is `a74c86b4f6d351e9d3c560bd95d722cc2d4394a2843fc9e4c02a9b8c427df42e`.

The report digest is `ea382924e317d66b89bbc2fe6a8e54c4d169776c0b7f596c0220fecbff739ba4`.

The receipt embeds the result and verifies both output digests.

## BOII provenance

The BOII record uses fold 2 and schema 2 timing fields.

The source issue is `2019-07-03T00:00:00Z`.

The archive availability is `2026-08-04T20:37:53.995950Z`.

The timing record does not claim operational issue-time availability.

The evidence document now lists target digest
`1d5570ab9baf7a4bb978be2069dbff8c89b0f88546442884556f37eb481eb43f`.

It lists evidence digest
`3e1f022ea7e0e6f280f9854adae7080f4c308b57da70a578ce9d6c10ae95b075`.

The verifier checks both document digests against the current files.

## Publication contracts

The claim generator reads Phase 2 rows, stations, bootstrap count, seeds, and
metrics from the result record.

It reads ETo seeds, replicates, support cells, and minimum support from the
evaluator record.

M2 scope is explicit in the manuscript, Markdown, generated report, and Figure 2.

The scope is B1, B2, and M1 through M3 on 7,923 common fitted-model rows.

B0 remains separate on 1,555 consecutive-day pairs.

Retrospective GEFS data uses source-issue-aligned retrospective reforecast wording.

The manuscript lists the public repository and two dataset DOIs:

- https://github.com/marco-trotta1/MLET
- https://doi.org/10.5281/zenodo.10119477
- https://doi.org/10.5281/zenodo.7636781

The Volk reference uses 2024, Nature Water, volume 2, number 2, pages 193 to 205,
and DOI `10.1038/s44221-023-00181-7`.

## Test-first evidence

The initial focused RED run reported 3 failures, 18 passes, and 1 warning.

The failures covered the schema parser contract and the stale receipt contract.

The final focused run reports 29 passes and 1 warning.

The verifier tests reject a changed receipt and a replaced generated claims file.

## Verification

The full suite reports 722 passes and 1 accepted NumPy binary-size warning.

`./scripts/verify_build_ready.sh` passes.

`PYTHONPATH=src python3 scripts/verify_arxiv_manuscript.py --pdf output/pdf/mlet_preprint.pdf`
passes.

`git diff --check` passes.

Tectonic compiles the manuscript with no LaTeX errors, undefined references,
undefined citations, or overfull boxes.

The PDF title is:

`MLET: Incremental Predictive Value of OpenET and an Auditable Reference-Evapotranspiration Outlook`

The PDF has 10 US Letter pages at 612 by 792 points.

The final PDF renders at 144 dpi for all 10 pages.

Visual inspection finds no clipping or collisions.

Pages 9 and 10 remain intentionally sparse ledger and reference pages.

The clean source archive compiles after extraction.

The primary and clean PDF text SHA-256 is
`1e0be96b5efa95e7f8b8e03f394b5990059ac7aa67fce0321dfc0fcb9d5e0ca7`.

Both builds have 10 pages and the exact PDF title.

The archive contains only relative paths.

## Remaining gate

The full reference-ETo hindcast remains pending.

The one-case BOII result remains a retrospective diagnostic.

Tectonic still reports environment font substitutions and underfull boxes.

These warnings do not indicate clipping, broken references, or failed compilation.

## Final fix wave · 2026-08-05

This wave closes the six residual review findings.

### RED evidence

The focused RED command was:

```text
PYTHONPATH=src python3 -m pytest -q tests/test_manuscript_artifacts.py tests/test_cli_phase2.py tests/test_build_arxiv_claims.py tests/test_build_arxiv_figures.py tests/test_verify_arxiv_manuscript.py
```

Collection stopped because `scripts.verify_arxiv_manuscript` lacked the new
`_verify_final_package` helper. The failure was expected for the new verifier tests.

### Changes

- Schema 1 preserves its legacy result shape. It no longer infers station count from model rows. Any downstream station claim now requires an explicit station count.
- M2 versus B2 reduction is generated from serialized model MAE values.
- Support figures derive cell, lead, season, fold, and observation dimensions from evaluator records.
- The abstract expands ASCE-EWRI and cites the ASCE standard on first use. Figure 1 expands ASCE-EWRI, ETo, and ETos labels.
- The verifier binds the final PDF to the tracked clean source tree and safe source archive. Build-ready verification invokes this package check.
- The clean source tree, source archive, figures, claims, and PDF were regenerated from canonical inputs.
- The claim ledger and bibliography now use a two-column flow with a controlled page break. Figure 2 remains on page 5. The PDF remains 10 US Letter pages.

### GREEN evidence

The focused regression command reports:

```text
33 passed, 1 warning in 4.70s
```

The full build-ready command reports:

```text
726 passed, 1 warning in 10.95s
== VERIFY PASSED ==
== BUILD READY: non-gated software and manuscript work passed ==
```

The manuscript verifier reports:

```text
MLET arXiv manuscript verification passed.
```

The package verifier rejects a truncated final PDF and a changed clean-source
claim file. The clean source compiles and its PDF text signature matches the final PDF.

The final PDF SHA-256 is
`b72983cdc728785a120cbbcdb5005e4ad05a607906120c0c6a718a0af256f5d6`.

The final PDF text signature is
`36ec39138df71fd8e7f829a81decf20e53e81079f38ba8e930fe4f4c9bd6cf70`.

The source archive SHA-256 is
`3d348d017683a7ac2c326176ea95ac3b05e4b852cb871233df77b27cb99c8431`.

The remaining gate is the full reference-ETo hindcast. The one-case BOII result
remains a retrospective diagnostic. Tectonic reports only environment font
substitutions and underfull boxes.

## Raster binding fix · 2026-08-05

The reviewer replaced page 1 with a visible red overlay while preserving PDF
text, page count, and title. The old verifier accepted that replacement.

### RED evidence

The new regression command initially reported:

```text
PYTHONPATH=src python3 -m pytest -q tests/test_verify_arxiv_manuscript.py -k visible_pdf_overlay
1 failed, 9 deselected
Failed: DID NOT RAISE <class 'ValueError'>
```

### Changes

`scripts/verify_arxiv_manuscript.py` now renders every PDF page with the
available `pdftoppm` renderer at a fixed 144 DPI. It hashes each PPM raster.
The final-package signature retains page count, extracted-text SHA-256, and
title checks. It now also compares all per-page raster hashes. A missing
renderer raises a clear verification error.

The regression suite adds visible-overlay and missing-renderer tests.

### GREEN evidence

The overlay regression now reports:

```text
PYTHONPATH=src python3 -m pytest -q tests/test_verify_arxiv_manuscript.py -k visible_pdf_overlay
1 passed, 10 deselected in 2.07s
```

The focused manuscript command reports:

```text
35 passed, 1 warning in 7.01s
```

The build-ready command reports:

```text
728 passed, 1 warning in 13.25s
== VERIFY PASSED ==
== BUILD READY: non-gated software and manuscript work passed ==
```

The standalone manuscript verifier passes. The extracted source archive
compiles to 10 US Letter pages. Primary and clean PDFs have equal page count,
text hash, title, and all 10 raster hashes at 144 DPI.
