# neuralhydrology provenance

Everything MLET took from neuralhydrology, what form it took, and where it lives.

## Upstream

- Repository: https://github.com/neuralhydrology/neuralhydrology
- Version: 1.13.0
- Commit: `d6d7aa5cc6d9e42308009139ccccf37be006445f` (2026-04-07)
- Licence: BSD-3-Clause
- Citation: Kratzert, F. et al. NeuralHydrology - A Python library for Deep
  Learning research in hydrology. *Journal of Open Source Software* (2022).
  doi:10.21105/joss.04050

The licence notice is retained with the ported source in
`src/mlet/reference/UPSTREAM.md`, as BSD-3-Clause requires.

## Two kinds of borrowing

**Ported** means upstream source was translated into MLET source; the licence
notice travels with it. **Reimplemented** means a design idea was adopted and the
code written independently against MLET's own contracts; no upstream code is
present. The distinction matters for both licensing and for what the manuscript
can claim as MLET's own work.

| MLET module | Upstream file | Form | What was taken |
|---|---|---|---|
| `src/mlet/reference/fao56_radiation.py` | `datautils/pet.py` | Ported | FAO-56 radiation chain: Eqs. 7, 8, 13, 21, 23, 24, 25, 37, 38, 39, 40, 48 |
| `src/mlet/reference/priestley_taylor.py` | `datautils/pet.py` | Ported | Priestley-Taylor PET total |
| `src/mlet/outlook/namespaces.py` | `utils/config.py` | Reimplemented | `hindcast_inputs` / `forecast_inputs` / `static_attributes` separation |
| `src/mlet/outlook/overlap.py` | `modelzoo/handoff_forecast_lstm.py` | Reimplemented | `forecast_overlap` disagreement, as a diagnostic rather than a regulariser |
| `src/mlet/outlook/scaler_artifact.py` | `datasetzoo/basedataset.py` | Reimplemented | Train-only scaler frozen to disk and required as an evaluation input |
| `src/mlet/hybrid/bounded.py` | `modelzoo/baseconceptualmodel.py` | Reimplemented | Bounded dynamic parameterization via sigmoid into a declared range |
| `src/mlet/hybrid/fao56_dual.py` | `modelzoo/shm.py` | Reimplemented | Conceptual model with externally supplied stress and drainage terms |
| `src/mlet/hybrid/torch_adapter.py` | `modelzoo/hybridmodel.py` | Reimplemented | Differentiable conceptual core taking per-timestep learned parameters |
| `src/mlet/hybrid/nh_export.py` | `datasetzoo/genericdataset.py` | Reimplemented | `time_series/<id>.nc` + `attributes/*.csv` layout, NaN for missing |

## Defects found in upstream and corrected here

Both were found by building the three-way reference-ET cross-check
(`mlet qc-eto`). Both are in `datautils/pet.py` at the reviewed commit. Neither
affects the LSTM models neuralhydrology is principally used for; both affect
anyone using its PET utilities.

### 1. Priestley-Taylor energy conversion applied twice

`get_priestley_taylor_pet` computes `(alpha / _lambda) * ... ` and then multiplies
by `0.408`. `alpha / _lambda` divides by the latent heat of vaporisation
(2.45 MJ kg⁻¹), and `0.408` is `1 / 2.45`. The conversion is applied twice, so
PET is understated by a factor of **2.451**.

On MLET's test fixture (2026-07-15, 43.6175°N, 824 m, Rs 28 MJ m⁻² d⁻¹,
Tmax 33 °C, Tmin 15 °C) upstream returns 2.5575 mm d⁻¹. The published form gives
6.2683 mm d⁻¹, which is 0.861 of the ASCE-PM short-reference ETo of
7.2813 mm d⁻¹ computed by vendored pyfao56 — the expected PT/PM relationship for
semi-arid advective conditions. 2.56 mm d⁻¹ for July in southern Idaho is not
physically plausible.

### 2. Clear-sky radiation elevation coefficient ten times too large

`_get_clear_sky_rad` computes `(0.75 + 2 * 10e-5 * elev)`. FAO-56 Eq. 37 is
`Rso = (0.75 + 2 × 10⁻⁵ z) Ra`. In Python `10e-5 == 1e-4`, so the coefficient is
`2e-4`. At 824 m this overestimates clear-sky radiation by **19.4%**, propagating
through Eq. 39 net longwave into net radiation and therefore into PET. The error
grows with elevation, so it is worst exactly where MLET operates.

### Disposition

Both are reported upstream. Regression tests in
`tests/test_reference_fao56_radiation.py` and
`tests/test_reference_priestley_taylor.py` pin the corrected values **and** the
ratio to the defective forms, so a future re-port cannot silently reintroduce
either.

## What MLET did not take

- **The LSTM model zoo.** MLET's research question is whether a visible water
  balance with small learned terms is competitive, so a pure sequence model is
  the comparison, not the method.
- **The metrics module.** Its 20 metrics are streamflow-specific (NSE, KGE,
  flow-duration curves, peak timing, baseflow index) and none applies to daily
  ET. It also contains no CRPS, so MLET's probabilistic scoring
  (`mlet.evaluate.mean_pinball_loss`) is its own.
- **`use_basin_id_encoding`.** Conditioning on entity identity rather than
  physical attributes would invalidate withheld-field evaluation.
  `src/mlet/hybrid/nh_export.py` refuses to write identifier-like attributes.
- **numba.** Not an MLET dependency; the ported functions are plain NumPy.

## Honest statement of the relationship

MLET is not a neuralhydrology fork and does not depend on it at runtime. It
adopted four design patterns, ported one set of published equations, and
corrected two defects in what it ported. The strongest published evidence
*against* MLET's central design assumption — that keeping the water balance
visible is worth the accuracy it costs — comes from the neuralhydrology CAMELS
results, and that is recorded in
[hybrid model scaffold](HYBRID_MODEL_SCAFFOLD.md) as a condition any future
hybrid result must address.
