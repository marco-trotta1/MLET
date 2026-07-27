# Task 6 report — probabilistic scoring primitives

Implemented the Task 6 probabilistic scoring primitives in `src/mlet/evaluate.py`:

- `pinball_loss(observed, predicted, quantile)`
- `mean_pinball_loss(observed, quantiles, levels)`
- `interval_coverage(observed, lower, upper)`
- `mean_interval_width(lower, upper)`

The implementation keeps the existing deterministic metrics unchanged and preserves the clarification that three predicted quantiles support a mean pinball loss, not CRPS.

Added deterministic coverage in `tests/test_evaluate_probabilistic.py` for:

- asymmetric pinball penalties
- exact-hit behavior
- mean pinball averaging over cases and levels
- sharper-vs-vaguer forecast ranking
- inclusive interval coverage
- mean interval width
- invalid interval bounds
- length / level mismatches
- empty-input rejection

Updated `docs/REPRODUCIBILITY.md` with the actual post-task test count: `408`.

Verification completed:

- Focused tests: `python3 -m pytest tests/test_evaluate_probabilistic.py -q`
  - Result: `9 passed`
- Full gate: `PYTHONPATH=src:vendor/pyfao56/src ./scripts/verify.sh`
  - Result: `408 passed, 1 warning`
  - Serving-path isolation: `ok`

Concern to carry forward:

- Running `./scripts/verify.sh` without the expected `PYTHONPATH=src:vendor/pyfao56/src` environment can fail an existing CLI smoke test because `python -m mlet` cannot see the source tree.
