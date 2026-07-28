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
- empty quantile-level rejection

Updated `docs/REPRODUCIBILITY.md` with the actual post-fix test count: `409`.

Verification completed after the empty-level guard fix:

- Focused tests: `python3 -m pytest tests/test_evaluate_probabilistic.py -q`
- Full gate: `PYTHONPATH=src:vendor/pyfao56/src ./scripts/verify.sh`

Exact focused-test output:

```text
..........                                                               [100%]
10 passed in 0.09s
```

Exact full-gate output:

```text
== python version ==
Python 3.13.5
== test suite ==
........................................................................ [ 17%]
........................................................................ [ 35%]
........................................................................ [ 52%]
........................................................................ [ 70%]
........................................................................ [ 88%]
.................................................                        [100%]
=============================== warnings summary ===============================
tests/test_cli_phase2.py::test_qc_gridmet_prints_mean_absolute_delta
  <frozen importlib._bootstrap>:488: RuntimeWarning: numpy.ndarray size changed, may indicate binary incompatibility. Expected 16 from C header, got 96 from PyObject

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
409 passed, 1 warning in 29.13s
== serving-path isolation ==
ok
== VERIFY PASSED ==
```

Concern to carry forward:

- Running `./scripts/verify.sh` without the expected `PYTHONPATH=src:vendor/pyfao56/src` environment can fail an existing CLI smoke test because `python -m mlet` cannot see the source tree.

Final follow-up verification (rerun immediately before commit):

- Focused command: `python3 -m pytest tests/test_evaluate_probabilistic.py -q`

```text
..........                                                               [100%]
10 passed in 0.08s
```

- Full-gate command: `PYTHONPATH=src:vendor/pyfao56/src ./scripts/verify.sh`

```text
== python version ==
Python 3.13.5
== test suite ==
........................................................................ [ 17%]
........................................................................ [ 35%]
........................................................................ [ 52%]
........................................................................ [ 70%]
........................................................................ [ 88%]
.................................................                        [100%]
=============================== warnings summary ===============================
tests/test_cli_phase2.py::test_qc_gridmet_prints_mean_absolute_delta
  <frozen importlib._bootstrap>:488: RuntimeWarning: numpy.ndarray size changed, may indicate binary incompatibility. Expected 16 from C header, got 96 from PyObject

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
409 passed, 1 warning in 27.62s
== serving-path isolation ==
ok
== VERIFY PASSED ==
```
