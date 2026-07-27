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

## Differentiable path

`src/mlet/hybrid/torch_adapter.py` is an optional PyTorch reimplementation of
the same eleven lines of FAO-56 arithmetic. The duplication is intentional:
there is no backend abstraction in the load-bearing physics code. Instead,
`tests/test_hybrid_torch_adapter.py::test_torch_forward_matches_the_numpy_balance`
asserts that the torch and NumPy paths agree to `1e-6` for identical drivers.

`drivers_to_tensor` produces an `(n_steps, 5)` tensor in `DailyStep` field order.
`torch_water_balance` returns `(n_steps, 3)` columns in the order
`eta_mm`, `deep_percolation_mm`, `depletion_mm`. Autograd reaches both learned
terms: `Ks` and the deep-percolation fraction. This is a gradient path for a
future experiment, not training code.

PyTorch is not a core dependency. It is available only through
`python -m pip install -e ".[hybrid]"`; the plain NumPy scaffold remains
importable without it. The CI hybrid leg installs that extra, runs the focused
tests, and then runs the canonical serving-path gate.

## Exporting to neuralhydrology

`src/mlet/hybrid/nh_export.py` writes MLET series in the `GenericDataset` layout:
one netCDF per site under `time_series/`, coordinate named `date`, static
attributes as CSV under `attributes/` indexed by site id, missing values as NaN.
Any neuralhydrology model can then be run against MLET data without modifying
the library.

Two refusals are deliberate. Sentinel values (`-999` and similar) are rejected,
because `GenericDataset` recognises only NaN as missing and would otherwise read
a sentinel as an observation. Attributes whose names look like entity
identifiers are rejected, because conditioning on site identity rather than
physical properties invalidates withheld-field evaluation—the evaluation the
MLET research question rests on. `use_basin_id_encoding` is the upstream
mechanism to avoid; EA-LSTM, which gates the input on static attributes, is the
one to prefer. The exporter also requires a sorted, unique index with exactly
one-day spacing, safe single-component site ids and filenames, shared attribute
keys, no identifier-like time-series columns, case-insensitive site uniqueness,
and exact series/attribute site coverage so an incomplete, colliding, or
escaping tree cannot be mistaken for a valid experiment. The declared export
root must be a real directory; existing `time_series/` and `attributes/`
directories must also be real directories, and existing final `.nc` or `.csv`
paths must be real files rather than symlinks or directories. These checks are
performed before xarray or pandas writes, so an export cannot follow a link out
of its declared tree or overwrite a target outside it. Case-insensitive
comparison is used for validation only; original site spelling is retained in
emitted paths and CSV indices when unique.
The identifier predicate also rejects generic identity fields (`id`, `site`,
`basin`, `station`) and common code/key forms such as `site_code`,
`entity_code`, `grid_id`, `cell_id`, and `field_id`, in both static and dynamic
features. Static attribute values must be scalar real numeric values (Python
or NumPy integers/floats); scalar NaN remains the missing-value marker, while
lists, strings, and other sequences are rejected. Before writing, existing
`time_series/` and `attributes/` paths must be real directories rather than
symlinks or files, and existing final output paths must be real files rather
than symlinks or directories. The root itself is also rejected when it is a
symlink. These checks happen before xarray/pandas writes, preventing an export
from escaping its declared root or overwriting an external symlink target.

## Isolation

`scripts/verify.sh` greps the serving path for imports of `torch` or
`mlet.hybrid` and fails the build if any appear. The authoritative
`tests/test_hybrid_isolation.py` walks the Python AST, including deferred
imports inside functions, and checks the same boundary. It also proves that
`mlet.hybrid.bounded` and `mlet.hybrid.fao56_dual` import on a plain install.
