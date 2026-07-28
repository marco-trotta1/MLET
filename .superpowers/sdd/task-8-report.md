# Task 8 report — bounded dynamic parameterization in the isolated hybrid tier

Date: 2026-07-27

## Scope completed

Implemented Task 8 only:

- created the new isolated `src/mlet/hybrid/` package
- added a frozen `ParameterRange` dataclass with `name`, `low`, `high`,
  `units`, and `citation`
- added a stable, overflow-free NumPy sigmoid helper
- added `bounded_parameter(raw, parameter_range)` for elementwise range mapping
- added `bounded_parameters(raw, ranges)` for column-wise mapping into named
  outputs
- defined the two shipped FAO-56 ranges needed by Task 9:
  - `FAO56_STRESS_RANGE`
  - `FAO56_DEEP_PERCOLATION_RANGE`
- added deterministic tests for:
  - extreme inputs staying inside bounds
  - midpoint behavior at zero
  - monotonicity
  - overflow-free behavior for very large magnitudes
  - per-column bounded mapping
  - shape validation
  - range validation
  - citation/units presence
- updated `docs/REPRODUCIBILITY.md` with the Task 8 test-count ledger row

No serving-path imports were added. The new package remains isolated from
`src/mlet/outlook`, `src/mlet/sources`, `src/mlet/experiments`, and
`src/mlet/cli.py`.

## Implementation notes

The mapping follows the brief’s declared-range logic:

`low + sigmoid(raw) * (high - low)`

The only numerical care needed is the sigmoid itself. I used a sign-split
implementation so that large negative values never send `exp(-x)` into an
overflow path. The result is then clipped to the declared bounds so the
extremes stay physically bounded even when the input diverges.

The shipped ranges are documented as constants with citations because the range
is the load-bearing part of the contract, not the learned raw output.

## Verification run

Focused task test:

- `python3 -m pytest tests/test_hybrid_bounded.py -q`
- result: `8 passed`

Full repository gate:

- `PYTHONPATH=src:vendor/pyfao56/src ./scripts/verify.sh`
- result: `419 passed, 1 warning`
- serving-path isolation: `ok`

I also ran the same gate without `PYTHONPATH` first and it failed in an
unrelated CLI entrypoint test because `mlet` was not importable in that shell
configuration. The documented `PYTHONPATH=src:vendor/pyfao56/src` setting
restored the expected repository state.

## Files changed

- `src/mlet/hybrid/__init__.py`
- `src/mlet/hybrid/bounded.py`
- `tests/test_hybrid_bounded.py`
- `docs/REPRODUCIBILITY.md`

## Commit

- `16f042e` — `feat: add bounded dynamic parameterization for learned physical terms`

## Review notes

The implementation stays intentionally small and reviewable:

- pure NumPy only
- no new dependencies
- no changes to serving, outlook, sources, experiments, or CLI code paths
- no Task 9 work started

## Review-fix verification update

The Task 8 review findings were fixed in `src/mlet/hybrid/bounded.py` and
covered by new tests in `tests/test_hybrid_bounded.py`.

Focused Task 8 test:

```text
..........                                                               [100%]
10 passed in 0.09s
```

Full repository gate:

```text
== python version ==
Python 3.13.5
== test suite ==
........................................................................ [ 17%]
........................................................................ [ 34%]
........................................................................ [ 51%]
..................................... [ 68%]
........................................................................ [ 85%]
.............................................................            [100%]
=============================== warnings summary ===============================
tests/test_cli_phase2.py::test_qc_gridmet_prints_mean_absolute_delta
  <frozen importlib._bootstrap>:488: RuntimeWarning: numpy.ndarray size changed, may indicate binary incompatibility. Expected 16 from C header, got 96 from PyObject

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
421 passed, 1 warning in 29.15s
== serving-path isolation ==
ok
== VERIFY PASSED ==
```

Actual counts after the fix:

- focused Task 8 tests: 10 passed
- full gate: 421 passed, 1 warning
