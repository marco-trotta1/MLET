# Task 15 calibration-guard report

## Scope

The lead-stratified split-conformal calibration helper now requires an explicit
strict-UTC `cutoff`. It rejects every calibration case whose
`target_available_at` is later than that cutoff before calling `predict_interval`
or computing nonconformity scores. The evaluator passes the frozen
`calibration_cutoff` from its validated split, so the temporal rule is enforced
both at archive validation and at the fitting boundary.

## Regression

The residual-model tests directly construct a valid fitted model, mutate a
calibration case's target receipt to 2099, and call the helper with the frozen
2023 calibration cutoff. The helper rejects the case before interval inflation.
All helper call sites now pass a cutoff explicitly.

## Verification

```text
python3 -m pytest tests/test_outlook_residual_model.py -q
18 passed

python3 -m pytest -q
354 passed, 1 known NumPy ABI warning

python3 -m compileall -q src tests
git diff --check
```

The warning is the pre-existing environment warning from
`tests/test_cli_phase2.py::test_qc_gridmet_prints_mean_absolute_delta`.
