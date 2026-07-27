# Reproducibility

Every number in the MLET manuscript must be regenerable from a clean clone by
the commands on this page. Nothing here requires private data.

## Environment

- Python: `>=3.9` (declared in `pyproject.toml`; CI verifies 3.9 and 3.12)
- Install: `python -m pip install -e .`
- Vendored FAO-56 implementation: `pyfao56` 1.4.3, upstream commit
  `1d242ee985be0edbc4946f06e7e94a487d4bc0c9`, provenance in
  `vendor/pyfao56/UPSTREAM.md`

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
| 1 | independent FAO-56 radiation chain | 366 |

## Regenerating published artifacts

- Phase 2 daily-ET comparison: see `docs/results/phase2_openet_value.md` header
- Idaho outlook candidate map: `python3 -m mlet publish-outlook --run OUTPUT_ROOT/RUN_ID`
  (always exits 1 by contract — the output is a research candidate)
- Residual-model experiment: `python3 -m mlet evaluate-outlook-residual --cases examples/outlook/hindcast_cases.json --out <path>`
