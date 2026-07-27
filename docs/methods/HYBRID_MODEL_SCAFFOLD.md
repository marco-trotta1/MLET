# Hybrid model scaffold

## Status

A physical scaffold with a validated seam for learned terms. It trains nothing,
fits nothing, and makes no ET prediction claim. No result in this repository
depends on it, and nothing in the serving path can import it.

## Design

`src/mlet/hybrid/fao56_dual.py` implements the FAO-56 dual-coefficient daily
water balance as a pure function, taking the water-stress coefficient `Ks` and
the deep-percolation fraction as per-timestep arguments rather than computing
them internally. Those are the two terms the MLET research question proposes to
learn, and they are the same two terms neuralhydrology's `SHM` exposes as
`ktetha` and `perc`.

Equations, all from FAO-56 (Allen et al., 1998), transcribed from vendored
pyfao56 `model.py`:

| Quantity | Equation |
|---|---|
| Total available water | Eq. 82 |
| Readily available water | Eq. 83 |
| Water-stress coefficient | Eq. 84 |
| Actual crop coefficient, actual ET | Eq. 80 |
| Deep percolation | Eq. 88 |
| Root-zone depletion | Eqs. 85, 86 |

## Why this is FAO-56 and not something wearing the name

`tests/test_hybrid_fao56_dual.py::test_default_parameters_reproduce_pyfao56_exactly`
asserts that with `ks=None` (FAO-56 Eq. 84) and `deep_percolation_fraction=1.0`
(the Eq. 88 default) the scaffold reproduces the pyfao56 depletion trajectory to
1e-12. The reference trajectory in that test is an independent transcription of
`vendor/pyfao56/src/pyfao56/model.py`, not a recording of this module's output.

The deterministic ten-day fixture uses rainfall `[0, 0, 18, 0, 0, 0, 0, 100,
0, 0]` mm. The second wetting event was corrected from 25 mm after review: with
25 mm, Eq. 88's `max(rain + irrigation - ETa - Dr, 0)` term is zero on every
day, so the test of a lower percolation fraction could not observe any
percolation. The 100 mm value creates genuine positive excess water while
leaving the production equation and the independent equivalence check
unchanged. This is a non-scientific fixture correction, not a claim about field
rainfall.

The actual vendored `pyfao56.Model` was also run over the same ten dates and
drivers (ETref 7 mm, the rainfall sequence above, constant soil parameters, and
constant-p mode). Its `Dr`, `DP`, and `Ks` trajectory is recorded in
`docs/REPRODUCIBILITY.md`; the scaffold's intentionally fixed `Kcb` and `Ke`
are the only simplifications needed to make the pure-function seam explicit.

Any future learned parameterisation is therefore a departure from a known
baseline whose magnitude is measurable, rather than an unquantified difference
between two similar-looking models.

## Bounded learned terms

Learned values must be mapped through `mlet.hybrid.bounded.bounded_parameter`
before reaching the balance. The balance validates the bounds and raises rather
than clipping, so an out-of-range learned term is a loud failure. `Ks` is bounded
to [0, 1] by FAO-56 Eq. 84 and the percolation fraction to [0, 1] by Eq. 88; both
bounds carry citations in source, and a test enforces that every shipped range
has one.

## The units guard

`SoilLimits` requires `units="mm"`. A water balance is mass-conservative, so
standardised depths destroy closure while the arithmetic continues to run. This
mirrors neuralhydrology's `custom_normalization` requirement on conceptual
models, which exists for the same reason.

## What would have to be true before this is used for anything

1. A learned parameterisation trained under the frozen holdout protocol in
   `docs/evaluation/OUTLOOK_RESIDUAL_MODEL_PROTOCOL.md`.
2. A preregistered comparison against the physics baseline and against the
   existing conformal residual model, scored on mean pinball loss, coverage, and
   interval width.
3. Evidence the hybrid framing beats a well-configured pure LSTM on the same
   splits, or an honest report that it does not. The neuralhydrology CAMELS
   results are the strongest published evidence that it may not, and that
   possibility is why the physics baseline stays the product path.

None of the above is in scope for the plan that created this scaffold.

## Isolation

`scripts/verify.sh` greps the serving path for imports of `torch` or
`mlet.hybrid` and fails the build if any appear.
`tests/test_hybrid_isolation.py` enforces the same boundary in the test suite.
