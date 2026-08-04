# MLET next steps — handoff context

Paste this into a new chat as the first message. It is self-contained.

## Where things stand (verified 2026-07-28)

- Repo: `/Users/marcotrotta/Desktop/MLET Code`
- The neuralhydrology adoption plan (`docs/superpowers/plans/2026-07-27-neuralhydrology-adoption.md`) is **fully executed**. All 14 tasks landed.
- **Merged to main.** PR #6 ("Adopt NeuralHydrology for hybrid evapotranspiration outlooks") and PR #7 (CI test deps) both merged 2026-07-28. `origin/main` is at `e7ce0ff`. Nothing outstanding.
- `./scripts/verify.sh` passes: **585 tests**, up from 357 at plan start. Serving-path isolation check green.
- New on main: `src/mlet/reference/` (independent FAO-56 radiation + Priestley-Taylor), `src/mlet/hybrid/` (bounded parameterization, differentiable FAO-56, torch adapter, GenericDataset export), `docs/methods/`, `docs/REPRODUCIBILITY.md`, `data/reference/external_sources.json`.
- If a local checkout shows the branch ahead of `main`, run `git fetch origin` first — local `main` goes stale.

## The two upstream bugs

Found in neuralhydrology 1.13.0 `datautils/pet.py`, commit `d6d7aa5cc6d9e42308009139ccccf37be006445f`. Both verified numerically. Both have regression tests in MLET.

**Defect 1 — clear-sky radiation, 10x elevation coefficient.**
`_get_clear_sky_rad` computes `(0.75 + 2 * 10e-5 * elev)`. FAO-56 Eq. 37 is `(0.75 + 2e-5 * z)`. `10e-5 == 1e-4`, so the coefficient is 2e-4. At 824 m it overestimates Rso by **19.4%**, propagating through Eq. 39 net longwave into PET. Error grows with elevation.

**Defect 2 — Priestley-Taylor energy conversion applied twice.**
`get_priestley_taylor_pet` computes `(alpha / _lambda) * ...` then multiplies by `0.408`. `alpha/_lambda` divides by lambda = 2.45 MJ/kg; `0.408` **is** 1/2.45. PET is understated by **2.451x**.

On the MLET fixture (2026-07-15, 43.6175 N, 824 m, Rs 28 MJ/m2/day, Tmax 33 C, Tmin 15 C): upstream returns 2.5575 mm/day. Published form gives 6.2683 mm/day, which is 0.861x the ASCE-PM 7.2813 mm/day from vendored pyfao56 — the expected PT/PM ratio for semi-arid advective conditions.

**Defect 2 blast radius:** `datautils/climateindices.py:71` calls `get_priestley_taylor_pet`. Line 172 computes `aridity = pet_mean / p_mean`. Both `pet_mean` and `aridity` are written as dynamic climate-index features (`new_features[i, 1]` and `[i, 2]`). Anyone who ran `precalculate_dyn_climate_indices` has both features **2.45x too small**.

**Fixing defect 2 is a behavior change** for existing users — cached climate indices become inconsistent with new runs. Must be flagged in the issue.

**Open question, do not assert:** `alpha = 1.26` is commented "Calibrated in CAMELS, here static." If that calibration ran against the doubly-converted PET, alpha may be absorbing the error.

## Email thread with Frederik Kratzert

Sent 2026-07-26. Reported **only defect 1** — defect 2 has never been reported. Kratzert replied 2026-07-28 (~10 hours later):

- "it seems like this is indeed a bug and I would love to see you open a PR to correct it"
- Did **not** answer the offer to contribute `FAO56(BaseConceptualModel)` upstream
- Did **not** answer the offer to review the frozen preregistration
- Said: "I'm not really sure what a 'preregistration' is or what you mean by 'visible water balance'"
- His substantive answer on hybrid-vs-LSTM: whether physical constraints are "worth it" depends on use; if a model wins on a carefully designed spatial/temporal test set, he sees no reason to prefer another for adhering to physical laws; and — the sharp part — "the inputs (and targets) usually have uncertainty attached to them, so the question often is if conserving the mass of uncertain inputs is a good idea in the first place"

**Why that last point matters:** MLET's README says irrigation must be *inferred* from soil-moisture rises precipitation cannot explain when grower records are absent. Conserving mass over an inferred inflow turns inference error into persistent state error. An LSTM can hedge; a hard balance cannot. This is the strongest external objection to MLET's central design assumption, from a named expert.

`CONTRIBUTING.rst` asks for a GitHub issue first, referenced from the PR. Regression tests belong in `test/test_datautils.py`, which currently covers only `utils.py` — MLET's would be the first PET coverage in the repo, which explains how both bugs survived.

## Next steps, ranked

MLET-side work is merged. Everything below is outward-facing or new science.

1. **File the neuralhydrology issue covering both defects, then the PR.** He is waiting and the thread is warm. Issue ~30 min, PR ~1 hour.
2. **Reply to Kratzert.** Report defect 2, drop the jargon he flagged, engage the uncertain-inputs critique. ~15 min.
3. **Update three docs** with what changed: `docs/methods/NEURALHYDROLOGY_PROVENANCE.md` (real disposition — maintainer confirmed defect 1, PR invited, 2026-07-28), `src/mlet/reference/UPSTREAM.md` (add the aridity/climate-indices blast radius), `docs/methods/HYBRID_MODEL_SCAFFOLD.md` (add Kratzert's uncertain-inputs objection, attributed). ~30 min.
4. **Preregister the stratified test his critique implies:** same splits, hybrid vs. LSTM, stratified by whether irrigation is recorded or inferred. If the hybrid only wins where records exist, that is the answer. Must be frozen *before* running. ~2 hours to write the preregistration.

## Standing constraints

- Read `DESIGN.md` before any visual or UI decision.
- No new core dependencies. torch stays in the `mlet[hybrid]` extra.
- Nothing under `src/mlet/outlook/`, `src/mlet/sources/`, `src/mlet/experiments/`, or `cli.py` may import `torch` or `mlet.hybrid`.
- No task may change `promotion`, `validation_status`, or `external_release_eligible` semantics, or make `publish-outlook` exit non-1.
- Academic work. Docs get overwritten when behavior changes, not appended to.
- Gate for everything: `./scripts/verify.sh`
