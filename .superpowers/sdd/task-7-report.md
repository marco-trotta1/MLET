# Task 7 report — probabilistic residual scores and preregistration amendment

Date: 2026-07-27

## Scope completed

Implemented Task 7 only:

- added `physical_pinball_mm` and `residual_pinball_mm` to `ResidualMetric`
- scored both residual-report arms with mean pinball loss in
  `src/mlet/experiments/idaho_outlook_residual.py`
- scored the physical baseline with a degenerate interval whose three published
  quantiles all equal `physical_p50`
- added residual markdown columns for both pinball scores plus the explanatory
  note that this is mean pinball loss over p10/p50/p90, a discrete CRPS
  approximation rather than CRPS itself
- amended `docs/evaluation/OUTLOOK_PREREGISTRATION.md` with a dated 2026-07-27
  amendment and a cross-reference from the frozen metric section
- updated `docs/evaluation/OUTLOOK_RESIDUAL_MODEL_PROTOCOL.md` to document why
  pinball is reported alongside coverage and interval width
- added the Task 7 reproducibility ledger row in `docs/REPRODUCIBILITY.md`
- extended `tests/test_outlook_residual_model.py` with Task 7-focused coverage

No thresholds, cutoffs, support minima, coverage target, coverage tolerance,
promotion semantics, validation semantics, or external-release semantics were
changed.

## Amendment choice

The brief says to replace CRPS wording in the preregistration, or to use a
dated amendment if the frozen-document form makes in-place editing ambiguous.

In the current repository revision, `docs/evaluation/OUTLOOK_PREREGISTRATION.md`
did not literally contain CRPS wording to replace. To avoid silently rewriting a
frozen document, I:

1. added a forward reference in the frozen metrics section
2. appended a dated amendment section at the end of the preregistration
3. stated explicitly that thresholds, cutoffs, splits, and gates are unchanged

I did not modify `docs/evaluation/PREREGISTRATION.md` because a repository-wide
search found no CRPS or “continuous ranked” wording there.

## Test/design ambiguity resolved

The brief’s sample test used `examples/outlook/hindcast_cases.json` to assert
that at least one metric row carries a pinball score. In the current tree that
fixture is the documented zero-case `software_fixture` smoke test:

- schema_version: 2
- evidence_classification: `software_fixture`
- cases: `[]`

That fixture cannot produce support-qualified scored metric rows by design, and
the protocol/docs already describe it as a zero-case smoke test. To preserve the
existing fixture contract, I kept the fixture-based check for report columns and
note, and used a temporary support-qualified evidence bundle inside the test for
the “both arms are scored” assertion.

## Verification run

Focused residual-model tests:

- `PYTHONPATH=src:vendor/pyfao56/src python3 -m pytest tests/test_outlook_residual_model.py -q`
- result: `21 passed`

Fixture report check:

- `PYTHONPATH=src:vendor/pyfao56/src python3 -m mlet evaluate-outlook-residual --cases examples/outlook/hindcast_cases.json --out /private/tmp/residual_check.md`
- exit code: `1` (expected non-serving candidate contract)
- verified generated report contains:
  - `physical pinball (mm/day)`
  - `residual pinball (mm/day)`
  - the explanatory pinball/CRPS note

Full gate:

- `MPLCONFIGDIR=/private/tmp/mpl-task7-final PYTHONPATH=src:vendor/pyfao56/src ./scripts/verify.sh`
- result: `411 passed, 1 warning in 27.72s`
- serving-path isolation: `ok`

## Files changed

- `src/mlet/experiments/idaho_outlook_residual.py`
- `tests/test_outlook_residual_model.py`
- `docs/evaluation/OUTLOOK_PREREGISTRATION.md`
- `docs/evaluation/OUTLOOK_RESIDUAL_MODEL_PROTOCOL.md`
- `docs/REPRODUCIBILITY.md`

## Review notes

Final diff review found no Task 7 blockers. The only notable issue was the
brief/fixture mismatch described above, which is documented here and preserved
in the implementation choice.
