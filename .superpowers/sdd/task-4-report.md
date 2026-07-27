# Task 4 report: forecast-overlap disagreement diagnostic and qc-overlap

## Scope implemented

- Added `src/mlet/outlook/overlap.py` with:
  - frozen `OverlapWindow`
  - frozen `OverlapDiagnostic`
  - `evaluate_overlap(window)`
  - constants `OVERLAP_MAD_MAX_MM = 1.5` and `OVERLAP_MAD_MIN_MM = 0.01`
- Added `qc-overlap` to `src/mlet/cli.py`
- Added focused tests:
  - `tests/test_outlook_overlap.py`
  - `tests/test_cli_qc_overlap.py`
- Updated documentation:
  - `docs/evaluation/OUTLOOK_RESIDUAL_MODEL_PROTOCOL.md`
  - `docs/REPRODUCIBILITY.md`

## Requirements mapping

### Overlap diagnostic

`evaluate_overlap`:

- requires `overlap_days >= 1`
- requires `len(observed) == overlap_days`
- requires `len(forecast) == overlap_days`
- requires observed and forecast windows to cover the same ordered valid dates
- rejects duplicate valid dates
- computes daily ETo with `eto_for_member`
- computes forecast-minus-observed differences
- returns:
  - `n_days`
  - mean absolute difference
  - signed bias
  - maximum absolute difference
  - verdict string

Verdicts are exactly:

- `suspiciously_identical` when MAD `< 0.01`
- `inconsistent` when MAD `> 1.5`
- `consistent` otherwise

### CLI

`mlet qc-overlap --window-json <path>`:

- parses the JSON payload into `WeatherMember` rows and an `OverlapWindow`
- prints the overlap summary and verdict
- exits `0` only for `consistent`
- exits `1` for the two non-consistent verdicts
- exits `2` on malformed input / file / validation errors, matching the existing QC-command pattern

## Validation note

The plan text and its first sample fixtures disagreed on how to test
"before issue time":

- the semantic requirement says every overlap day must end before `issue_time`
- the sample implementation used `idaho_local_day_end_utc(day) > issue_time`
- the original sample passing fixture used `issue_time = 2026-07-15T00:00:00+00:00`
  with overlap dates including `2026-07-14`, which would fail that rule because
  the July 14 Idaho-local day had not ended yet

Per the task clarification, implementation keeps the semantic requirement and
the fixtures are corrected instead. The non-scientific overlap fixtures now use
`issue_time = 2026-07-15T12:00:00+00:00`, which is after the July 14 Idaho-local
day ends, while the after-issue rejection case still uses July 16 to prove that
post-issue overlap days fail with the required `before issue_time` message.

## Focused verification

- Red step:
  - `python3 -m pytest tests/test_outlook_overlap.py -q`
  - failed with `ModuleNotFoundError: No module named 'mlet.outlook.overlap'`
- Green step:
  - `python3 -m pytest tests/test_outlook_overlap.py -q`
  - result after implementation: `5 passed in 15.85s`
  - result after plan-fixture correction: `5 passed in 14.69s`
- CLI step:
  - `python3 -m pytest tests/test_cli_qc_overlap.py -q`
  - result after implementation: `2 passed in 17.09s`
  - result after plan-fixture correction: `2 passed in 16.01s`

## Full gate

- Verification command:
  - `PYTHONPATH=src:vendor/pyfao56/src ./scripts/verify.sh`
- Result:
  - `390 passed, 1 warning`
  - `== serving-path isolation ==`
  - `ok`
  - `== VERIFY PASSED ==`
  - wall time on final rerun: `25.39s`

## Here’s what I changed, here’s how I verified it

I added the forecast-overlap disagreement diagnostic, exposed it through the
new `qc-overlap` CLI, added deterministic focused tests, and updated the
residual-model and reproducibility docs, including the Task 4 test-count ledger row.

I verified it by:

- confirming the new tests failed before implementation
- running the new overlap unit tests to `5 passed`
- running the new CLI tests to `2 passed`
- planning a full `./scripts/verify.sh` gate before commit
