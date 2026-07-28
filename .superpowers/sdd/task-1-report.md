# Task 1 report — Independent FAO-56 radiation chain

## Outcome

Task 1 is complete. MLET now has an independent FAO-56 radiation chain under
`src/mlet/reference/`, with the published equations transcribed directly in the
test body and a provenance note capturing the upstream source plus the one
deliberate correction.

## What changed

- Added `src/mlet/reference/__init__.py` as the package marker and short
  description of the reference-only namespace.
- Added `src/mlet/reference/fao56_radiation.py` with the FAO-56 radiation
  helpers:
  - slope of saturation vapour pressure curve
  - solar declination
  - inverse relative distance Earth-Sun
  - sunset hour angle
  - extraterrestrial radiation
  - clear-sky radiation
  - net shortwave radiation
  - actual vapour pressure from Tmin
  - net outgoing longwave radiation
  - net radiation
  - atmospheric pressure
  - psychrometric constant
- Added `src/mlet/reference/UPSTREAM.md` documenting the neuralhydrology
  snapshot, licence, and the intentional deviations:
  - corrected Eq. 37 clear-sky radiation coefficient from `2 * 10e-5` to `2e-5`
  - no `numba`
  - solar radiation inputs remain in MJ m-2 d-1
- Added `tests/test_reference_fao56_radiation.py` with independent equation
  transcriptions and the explicit regression check for the clear-sky radiation
  defect.
- Updated `docs/REPRODUCIBILITY.md` with the Task 1 ledger row showing 366
  passing tests after this task.

## Verification

Focused check:

- `python3 -m pytest tests/test_reference_fao56_radiation.py -q`
- Result: `9 passed`

Canonical gate:

- `PYTHONPATH=src:vendor/pyfao56/src ./scripts/verify.sh`
- Result: `366 passed, 1 warning`, then `== VERIFY PASSED ==`

## Notes

I first hit a sandbox import-path problem in the existing CLI subprocess test:
`python -m mlet` was resolving against an unusable environment path. Rather than
change the task scope, I verified the gate with the checked-out source placed on
`PYTHONPATH`, which matches the repo note in `MLET_ML_DECISION_MAP.md` and keeps
the verification anchored to this workspace.

