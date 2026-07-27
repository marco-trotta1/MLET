# neuralhydrology upstream snapshot

`fao56_radiation.py` and `priestley_taylor.py` are ports of
`neuralhydrology/datautils/pet.py`.

## Source

- Repository: https://github.com/neuralhydrology/neuralhydrology
- Upstream commit: `d6d7aa5cc6d9e42308009139ccccf37be006445f`
- Upstream commit date: 2026-04-07 09:35:15 +0200
- Upstream version: `1.13.0`
- Licence: BSD-3-Clause

## Licence notice

BSD 3-Clause License. Copyright (c) 2021, NeuralHydrology. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

## Deliberate deviations

### 1. Clear-sky radiation elevation coefficient — upstream defect, corrected

Upstream `_get_clear_sky_rad` computes:

    cs_rad = (0.75 + 2 * 10e-5 * elev) * et_rad

In Python `10e-5 == 1e-4`, so the elevation coefficient is `2e-4`. FAO-56
Eq. 37 gives `Rso = (0.75 + 2 x 10^-5 z) Ra`, i.e. `2e-5`. Upstream's
coefficient is **ten times the published value**. At 824 m elevation this
overestimates clear-sky radiation by 19.4%, which propagates through Eq. 39
net longwave radiation into every Priestley-Taylor PET estimate at non-trivial
elevation.

MLET implements the published `2e-5`. `tests/test_reference_fao56_radiation.py`
asserts both the correct value and the 1.1935 ratio to the upstream form, so the
defect cannot be silently reintroduced by a future re-port.

This was reported upstream; see `docs/methods/NEURALHYDROLOGY_PROVENANCE.md`
for the disposition.

### 2. numba removed

Upstream decorates every function with `@numba.njit`. numba is not an MLET
dependency and these functions run over arrays of at most 20 days x a few
thousand grid cells, where the JIT cost exceeds the benefit. The ports are
plain NumPy and are array-safe by `np.asarray` coercion.

### 3. Solar radiation units

Upstream `get_priestley_taylor_pet` takes `s_rad` in W m-2 and converts
internally with `s_rad * 0.0864`. MLET's `WeatherMember.solar_mj_m2_day` is
already MJ m-2 d-1, so the ports take MJ m-2 d-1 and omit the conversion.
Passing W m-2 to these functions silently produces PET roughly 11.6x too large;
callers must use the documented unit.

### 4. Priestley-Taylor alpha

Upstream hardcodes `alpha = 1.26` with the comment "Calibrated in CAMELS, here
static". MLET exposes `alpha` as an explicit keyword argument defaulting to
1.26 so that the CAMELS provenance of the default is visible at the call site.

## Local scope

Only the radiation and PET equations were ported. Nothing else from
neuralhydrology is vendored. Patterns adopted by reimplementation rather than
copying (bounded dynamic parameterization, hindcast/forecast namespaces, the
frozen-scaler contract, the GenericDataset layout) are documented in
`docs/methods/NEURALHYDROLOGY_PROVENANCE.md`, not here.
