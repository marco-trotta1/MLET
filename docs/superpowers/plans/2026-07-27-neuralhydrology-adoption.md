# NeuralHydrology adoption — completed execution record

Source plan: `/Users/marcotrotta/Desktop/MLETp5.md`.

This file is the repository-local completion record for the plan. The external
plan remains the detailed task specification; this record preserves the
implementation order, manuscript-facing decisions, verification counts, and
the final evidence trail in the repository.

## Completion checklist

- [x] Task 0 — establish the reproducibility baseline and canonical
  verification gate.
- [x] Task 1 — add an independent FAO-56 radiation reference implementation
  ported from neuralhydrology PET utilities.
- [x] Task 2 — add Priestley-Taylor PET and the three-way ETo cross-check;
  record the upstream double-conversion defect and corrected relationship.
- [x] Task 3 — separate hindcast, forecast, and static feature namespaces;
  validate the contract and provenance metadata.
- [x] Task 4 — add the forecast-overlap disagreement diagnostic and CLI check.
- [x] Task 5 — freeze train-only normalization as a required, hashed JSON
  artifact.
- [x] Task 6 — add probabilistic scoring primitives: mean pinball loss,
  interval coverage, and interval width.
- [x] Task 7 — report pinball scores for both residual arms and amend the
  preregistration language.
- [x] Task 8 — add bounded dynamic parameterization in the isolated hybrid
  tier, including explicit unit and range validation.
- [x] Task 9 — add the FAO-56 dual-coefficient water-balance scaffold and
  validate its trajectory and mass closure against vendored pyfao56.
- [x] Task 10 — add the optional differentiable Torch adapter, gradient checks,
  and serving-path isolation enforcement.
- [x] Task 11 — add and harden the neuralhydrology GenericDataset exporter:
  layout, NaN/sentinel handling, identifier refusal, full preflight, coverage,
  safe paths, and documented non-race-safe symlink boundary.
- [x] Task 12 — register Caravan, Caravan MultiMet, and neuralhydrology as
  reviewed external sources; document why they are not ingested and preserve
  the ERA5-Land PET warning.
- [x] Task 13 — create the complete neuralhydrology provenance map, retain the
  BSD-3-Clause notice, distinguish ported code from reimplemented patterns,
  record both corrected PET defects, and reconcile README/reproducibility
  documentation.

## Verification ledger

| Checkpoint | Passing tests | Evidence |
|---|---:|---|
| Baseline / Task 0 | 357 | `608da8e` |
| Task 1 | 366 | `d3092b7` |
| Task 2 | 376 | `938f51d` |
| Task 3 | 383 | `544ea7f` |
| Task 4 | 392 | `ba6e711` |
| Task 5 | 399 | `13814a5` |
| Task 6 | 409 | `0fe931d` |
| Task 7 | 411 | `1981bf5` |
| Task 8 | 421 | `67b2463` |
| Task 9 | 432 | `c2e822b` |
| Task 10 | 467 | `691e53a` |
| Task 11 final | 567 | `ba92822` |
| Task 12 final | 573 | `f1976fe` |
| Task 13 final | 585 | `78f3e0a` |

The canonical local command is:

```bash
PYTHONPATH=src:vendor/pyfao56/src ./scripts/verify.sh
```

The plain command is the documented post-install form. The local workspace
does not expose the editable-install console entry point to child processes,
so the explicit `PYTHONPATH` is required here. The optional Torch path is
isolated from the serving path and is exercised by the hybrid CI extra.

## Manuscript-facing decisions retained

- MLET is not a neuralhydrology fork and does not depend on it at runtime.
- The FAO-56 radiation and Priestley-Taylor equations are ported reference
  implementations; the remaining neuralhydrology relationships are explicitly
  documented as independent reimplementations of selected design patterns.
- The upstream Priestley-Taylor double energy-to-depth conversion understates
  PET by 2.451; the upstream Eq. 37 elevation coefficient is ten times too
  large and overstates clear-sky radiation by 19.4% at the 824 m fixture.
- The hybrid code is a validated, non-serving scaffold with a differentiable
  path; it is not training code and no published result depends on it.
- Caravan and Caravan MultiMet are reviewed conventions and documented
  external references, not ingested evaluation data, because their basin/
  streamflow entity keys do not map onto MLET's grid-cell/station ET targets.
- GenericDataset export refuses identity-like fields because site identity
  would invalidate withheld-field evaluation; it writes NaN for missing values
  and rejects upstream sentinel values.

## Final review status

Every task was implemented in order, reviewed after implementation, and
committed. The final provenance pairing test checks exact MLET-module to
upstream-file rows. User-owned pre-existing untracked artifacts were preserved
and are intentionally not part of this execution record.
