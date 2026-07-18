# Task 16: Correct ETo date terminology

## Scope

Updated the `summarize_member_groups` docstring in `src/mlet/outlook/eto.py` to
describe `valid_date` as an Idaho-local calendar date under the shared
`America/Boise` outlook convention. The correction is documentation-only; no
runtime behavior or data contracts changed.

## Verification

- `python3 -m pytest -q tests/test_outlook_eto.py` — 9 passed.
- `python3 -m compileall -q src` — passed.
- `git diff --check` — passed.

## Review notes

The wording now explicitly distinguishes the outlook's Idaho-local civil-day
label from a UTC-day aggregation label, matching `docs/outlook/PRODUCT_CONTRACT.md`
and `src/mlet/outlook/dates.py`.
