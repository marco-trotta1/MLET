# Task 15 implementation report — receipt-bound residual targets

## Scope

The non-serving Idaho residual-model lane now treats target observations as
time-indexed evidence. A `ResidualCase` requires a strict-UTC
`target_available_at` after the Idaho-local valid day. Training rows are
accepted only when that target is available by `train_cutoff`; calibration rows
are accepted only when it is available by `calibration_cutoff`. Test targets may
arrive later for scoring, but remain receipt-bound.

Real archived cases must provide a relative, SHA-256-addressed
`target_receipt` artifact. Its exact schema binds the residual case, Task 8
case digest, layer, target kind, lead, valid date, spatial block, target value,
target availability time, URI, and source revision. The evaluator validates the
receipt bytes, all bindings, and the cutoff gates before fitting. Target
availability and target-receipt digests are retained in the canonical report
metadata and row digest.

The target receipt is archive-local evidence, not a release authority. The
existing independent archive-reconstruction and separately trusted release
authority blockers remain mandatory; no local path can emit promotion or
external eligibility. Software fixtures remain explicitly non-scientific and
false-only.

## Regressions

- train-target availability after the train cutoff is rejected;
- calibration-target availability after the calibration cutoff is rejected;
- a valid content-addressed target receipt is accepted by the receipt verifier;
- missing, mutated, and wrong-Task-8-case receipts fail closed;
- target availability and receipt metadata are present in the candidate report;
- direct model fitting also rejects training targets available after its cutoff.

## Verification

```text
python3 -m pytest tests/test_outlook_residual_model.py -q
17 passed

python3 -m pytest -q
353 passed, 1 known NumPy ABI warning

python3 -m compileall -q src tests
git diff --check
```

The NumPy warning is the pre-existing environment warning from
`tests/test_cli_phase2.py::test_qc_gridmet_prints_mean_absolute_delta`; it does
not fail the suite.
