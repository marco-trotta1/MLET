# Reproducibility

Every number in the MLET manuscript must be regenerable from a clean clone by
the commands on this page. Nothing here requires private data.

## Environment

- Python: `>=3.9` (declared in `pyproject.toml`; CI verifies 3.9 and 3.12)
- Install: `python -m pip install -e .`
- Vendored FAO-56 implementation: `pyfao56` 1.4.3, upstream commit
  `1d242ee985be0edbc4946f06e7e94a487d4bc0c9`, provenance in
  `vendor/pyfao56/UPSTREAM.md`
- Residual-model normalisation is a frozen JSON artifact, SHA-256 hashed and
  recorded in the run receipt. Reproducing a published interval requires the
  artifact, not just the code and seed.

## Single verification command

```bash
./scripts/verify.sh
```

This runs the full test suite and the serving-path isolation check. It is the
only gate that matters; CI runs exactly this.

Running `pytest` directly also works because `pyproject.toml` puts both `src`
and `vendor/pyfao56/src` on `pythonpath`. Before 2026-07-27 it did not, and a
fresh clone failed to collect 7 test modules — if you are reading an older
revision, that is why.

## Test-count ledger

Each row is recorded when the corresponding plan task lands. A task that does
not raise the count has added no executable evidence, which is a review finding.

| Task | Description | Tests passing after |
|---|---|---|
| baseline | before this plan | 357 |
| 0 | reproducibility baseline | 357 |
| 1 | independent FAO-56 radiation reference | 366 |
| 2 | Priestley-Taylor PET and three-way ETo cross-check | 376 |
| 3 | hindcast / forecast / static namespaces and provenance validation | 383 |
| 4 | forecast-overlap disagreement diagnostic and qc-overlap CLI | 392 |
| 5 | frozen train-only scaler artifact and required prediction-time use | 399 |
| 6 | probabilistic scoring primitives: pinball loss, interval coverage, width | 409 |
| 7 | residual-report pinball scores and preregistration amendment | 411 |
| 8 | bounded dynamic parameterization in isolated hybrid tier | 421 |

## Regenerating published artifacts

- Phase 2 daily-ET comparison: see `docs/results/phase2_openet_value.md` header
- Idaho outlook candidate map: `python3 -m mlet publish-outlook --run OUTPUT_ROOT/RUN_ID`
  (always exits 1 by contract — the output is a research candidate)
- Residual-model experiment: `python3 -m mlet evaluate-outlook-residual --cases examples/outlook/hindcast_cases.json --out <path>`
- Reference-ET cross-check: `python3 -m mlet qc-eto --member-json <path>`
  (exits 0 when the ASCE paths agree exactly and PT/ASCE-PM is inside the
  documented 0.60-1.05 band)
- Overlap consistency: `python3 -m mlet qc-overlap --window-json <path>`
  (exit 0 only when the verdict is `consistent`)
