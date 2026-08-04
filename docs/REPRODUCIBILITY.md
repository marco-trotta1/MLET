# Reproducibility

Every generated number in the MLET manuscript must be regenerable from a clean
clone by the commands on this page. The committed Phase 2 record includes an
independent reproduction receipt.

## Environment

- Python: `>=3.9` (declared in `pyproject.toml`; CI verifies 3.9 and 3.12)
- Install for verification: `python -m pip install -e ".[test]"`
- Runtime-only install: `python -m pip install -e .`
- The optional `test` extra supplies the `pytest` runner used by
  `scripts/verify.sh`; the hybrid CI job installs `.[hybrid,test]`.
- Vendored FAO-56 implementation: `pyfao56` 1.4.3, upstream commit
  `1d242ee985be0edbc4946f06e7e94a487d4bc0c9`, provenance in
  `vendor/pyfao56/UPSTREAM.md`
- Residual-model normalisation is a frozen JSON artifact, SHA-256 hashed and
  recorded in the run receipt. Reproducing a published interval requires the
  artifact, not just the code and seed.

## Single verification command

Use `./scripts/verify.sh` for the code suite and serving-path isolation check.
It also builds the committed real ETo candidate through the static-site path.

The committed candidate files are
`data/outlook/gefs_reforecast_20190703_outlook.json` and
`data/outlook/gefs_reforecast_20190703_manifest.json`.
Run `python3 scripts/verify_real_candidate_site.py` to check their clean-clone
site build directly.

To build a site from an external candidate directory, run:

```bash
python3 scripts/build_eto_site.py \
  --source-dir "/path/to/candidate" \
  --out _site-eto
```

The source directory must contain `outlook.json` and `manifest.json`.

Use `./scripts/verify_build_ready.sh` for the non-gated software and manuscript
draft gate. It checks the AgriMet station snapshot, deterministic Phase 2
artifacts, and manuscript sources. It does not assume an institutional storage
or compute allocation.

Use `./scripts/verify_manuscript_ready.sh` for the manuscript gate. It also
regenerates and byte-compares the committed Phase 2 and ETo Markdown, CSV, and
SVG artifacts. It fails until `docs/results/idaho_eto_hindcast.json` exists.
This failure is expected before the archived ETo evaluation is complete.

The ETo software fixture is `examples/outlook/eto_hindcast_evidence.json`.
The deferred residual-model fixture is
`examples/outlook/residual_model_evidence.json`. Neither fixture is scientific
evidence.

To reproduce Phase 2 without the separate gridMET quality-control archive, run:

```bash
python3 scripts/fetch_data.py --phase2-only
```

The command checks the two pinned archive checksums before extraction.

After building the interim dataset, run `mlet evaluate` with `--result-json`,
`--data-manifest`, and `--git-revision`. The command writes the strict Phase 2
result JSON that the manuscript artifact generator accepts.

Running `pytest` directly also works after installing the `test` extra because
`pyproject.toml` puts both `src` and `vendor/pyfao56/src` on `pythonpath`.
Before 2026-07-27 it did not, and a fresh clone failed to collect 7 test
modules — if you are reading an older revision, that is why.

GitHub-hosted runners attach ACL metadata to the checkout and temporary
directories. CI provisions `/mlet-pytest` as an ACL-free parent and uses its
`run` child as pytest's removable base temporary directory, so the output-root
trust checks remain enabled. `TMPDIR` points to the same trusted parent so CLI
tests and pytest agree on the permitted local temporary directory. Site-builder
tests also pass that trusted directory through the explicit scratch option.

## Test-count ledger

Each row is recorded when the corresponding plan task lands. A task that does
not raise the count has added no executable evidence, which is a review finding.

| Task | Description | Tests passing after |
|---|---|---|
| baseline | before this plan | 357 |
| 0 | reproducibility baseline | 357 |
| 1 | independent FAO-56 radiation reference | 366 |
| 2 | Priestley-Taylor PET and three-way ETo cross-check | 376 |
| 3 | hindcast / forecast / static namespaces and provenance validation | 383 |
| 4 | forecast-overlap disagreement diagnostic and qc-overlap CLI | 392 |
| 5 | frozen train-only scaler artifact and required prediction-time use | 399 |
| 6 | probabilistic scoring primitives: pinball loss, interval coverage, width | 409 |
| 7 | residual-report pinball scores and preregistration amendment | 411 |
| 8 | bounded dynamic parameterization in isolated hybrid tier | 421 |
| 9 | FAO-56 dual-coefficient scaffold with bounded learned seams | 432 |
| 10 | differentiable torch adapter, optional extra, and AST isolation enforcement | 467 |
| 11 | neuralhydrology GenericDataset export layout and validation | 567 |
| 12 | external reference-source registry for Caravan, Caravan MultiMet, and neuralhydrology | 573 |
| 13 | complete neuralhydrology provenance documentation and corrected-defect record | 585 |

Task 10 adds 35 passing structural/executable checks locally. The four torch
tests are optional at the local level: they pass when `mlet[hybrid]` is
installed and are reported as skipped when PyTorch is absent. The CI
`test-hybrid` job installs the extra and exercises the torch path.

## GenericDataset export audit trail

Task 11's `mlet.hybrid.nh_export` adapter is a plain-install boundary: it uses
the existing xarray/pandas stack and imports no PyTorch. For each site it writes
`time_series/<site_id>.nc` with a `date` coordinate and writes physical static
attributes to `attributes/attributes.csv` with `site_id` as the CSV index. The
site id is a row key only; it is never emitted as a model feature.

The focused exporter checks round-trip NaN preservation, rejection of the three
known GenericDataset sentinels (`-999`, `-9999`, and `-99.999`), sorted, unique,
strictly one-day-spaced dates, safe single-component site ids and filenames,
shared attribute names, identifier-like attribute names in both static and
time-series fields, generic identifier names and code/key forms in both static
and time-series fields, numeric-string time-series rejection, scalar numeric
static values, case-insensitive site uniqueness, exact site coverage, complete
preflight validation before writing, and rejection of a symlinked export root,
pre-existing symlinked or non-directory `time_series/` and `attributes/` output
paths, and symlinked or non-file final `.nc`/`.csv` outputs. These path checks
reject pre-existing symlink paths immediately before the corresponding xarray or
pandas write. They define the normal single-process boundary, not a concurrent
race-safe filesystem guarantee. The full canonical gate completed with 567
passing tests; the local verification environment had the optional PyTorch
extra installed.
Case-insensitive matching is used only for collision/coverage validation; the
original spelling is retained in each emitted path or CSV index when unique.
This is intentional defensive validation: GenericDataset treats a sentinel as an
observed number rather than a missing value, and either an identifier feature or
incomplete site coverage would change the meaning of a withheld-field evaluation.

## External reference-source registry audit trail

Task 12 adds the documentation-only registry
`data/reference/external_sources.json`, following the existing
`data/outlook/source_registry.json` schema. It records Caravan v1.5 as a
reviewed external benchmark, including the warning not to use the unreliable
ERA5-Land native `potential_evaporation` band; Caravan's FAO
Penman-Monteith PET variable is the recorded replacement. It records Caravan
MultiMet as the convention for pairing observed forcings with multiple
nowcasts/forecasts at a fixed issue time, and neuralhydrology 1.13.0 as the
software provenance source for the ported implementations and adopted patterns.

None of these sources is ingested. Caravan and Caravan MultiMet are basin- and
streamflow-keyed rather than grid-cell/station ET-keyed, while neuralhydrology
is a software library. The focused registry suite has 6 passing structural
checks, including the exact three-source set and the pinned neuralhydrology
1.13.0 review commit. The canonical gate after Task 12 has 573 passing tests,
one existing NumPy warning, and a passing serving-path isolation check. No
network or download behavior was added.

## Provenance

- Borrowed code and patterns: [neuralhydrology provenance](methods/NEURALHYDROLOGY_PROVENANCE.md)
- Vendored FAO-56 implementation: `vendor/pyfao56/UPSTREAM.md`
- Ported reference implementations and licence notice: `src/mlet/reference/UPSTREAM.md`
- External sources reviewed but not ingested: `data/reference/external_sources.json`

## Hybrid scaffold audit trail

The Task 9 scaffold is documented in `docs/methods/HYBRID_MODEL_SCAFFOLD.md`.
Its load-bearing check is:

```bash
python3 -m pytest tests/test_hybrid_fao56_dual.py -q
```

That file proves three things:

- with `ks=None` and `deep_percolation_fraction=1.0`, the depletion trajectory
  matches an independent transcription of vendored `pyfao56` to `1e-12`
- out-of-range learned terms are rejected loudly rather than silently clipped
- the mass-conservative balance refuses standardised units

The ten-day fixture's second wetting event is 100 mm. An earlier 25 mm draft
was internally impossible for the non-scientific partial-percolation assertion:
the Eq. 88 excess term stayed at zero for all ten days. The fixture was corrected
only to create a genuine excess-water case; no production equation was changed.

The independent transcription and the actual vendored `pyfao56.Model` were
also checked over the same dates and drivers. The vendored model's full output
is intentionally not treated as a bit-for-bit oracle for the scaffold because
it computes its own surface evaporation coefficient and crop-stage dynamics;
the load-bearing bit-for-bit check remains the independent Eq. 82--88
transcription in the focused test.

The actual-model cross-check was run with the vendored package (using
`MPLCONFIGDIR=/tmp/mlet-mpl` only to keep its plotting cache out of the
workspace):

```bash
MPLCONFIGDIR=/tmp/mlet-mpl PYTHONPATH="src:vendor/pyfao56/src" python3 - <<'PY'
import numpy as np
import pandas as pd
from pyfao56 import Model, Parameters, Weather

rain = [0.0, 0.0, 18.0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0]
keys = [f"2026-{day:03d}" for day in range(1, 11)]
weather = Weather()
weather.rfcrp = "S"
weather.wndht = 2.0
weather.wdata = pd.DataFrame(
    {"Srad": np.nan, "Tmax": np.nan, "Tmin": np.nan, "Vapr": np.nan,
     "Tdew": np.nan, "RHmax": np.nan, "RHmin": 45.0, "Wndsp": 2.0,
     "Rain": rain, "ETref": 7.0, "MorP": "M"}, index=keys)
params = Parameters(
    Kcmini=1.05, Kcmmid=1.05, Kcmend=1.05,
    Kcbini=1.05, Kcbmid=1.0500000001, Kcbend=1.05,
    Lini=25, Ldev=50, Lmid=50, Lend=25, hini=1.0, hmax=1.0,
    thetaFC=0.28, thetaWP=0.13,
    theta0=0.28 - 40.0 / (1000.0 * 1.2),
    Zrini=1.2, Zrmax=1.2, pbase=0.55)
model = Model("2026-001", "2026-010", params, weather, cons_p=True)
model.run()
for key, row in model.odata.iterrows():
    print(f"{key} ETa={row['ETa']:7.4f} DP={row['DP']:7.4f} "
          f"Dr={row['Dr']:8.4f} Ks={row['Ks']:6.4f}")
PY
```

Recorded output:

```text
2026-001 ETa= 7.3500 DP= 0.0000 Dr= 47.3500 Ks= 1.0000
2026-002 ETa= 7.3500 DP= 0.0000 Dr= 54.7000 Ks= 1.0000
2026-003 ETa= 7.3500 DP= 0.0000 Dr= 44.0500 Ks= 1.0000
2026-004 ETa= 8.4001 DP= 0.0000 Dr= 52.4501 Ks= 1.0000
2026-005 ETa= 8.4001 DP= 0.0000 Dr= 60.8502 Ks= 1.0000
2026-006 ETa= 8.4001 DP= 0.0000 Dr= 69.2503 Ks= 1.0000
2026-007 ETa= 8.4001 DP= 0.0000 Dr= 77.6504 Ks= 1.0000
2026-008 ETa= 8.4001 DP=13.9496 Dr=  0.0000 Ks= 1.0000
2026-009 ETa= 8.4001 DP= 0.0000 Dr=  8.4001 Ks= 1.0000
2026-010 ETa= 8.4001 DP= 0.0000 Dr= 16.8002 Ks= 1.0000
```

This confirms the expected qualitative behavior. The actual package computes
its surface-evaporation `Ke` and crop-stage terms, so its ETa values are not
expected to be identical to the scaffold's intentionally supplied fixed
`Kcb=1.05` and `Ke=0.12`; the independent Eq. 82--88 test is the numerical
equivalence gate.

## Regenerating published artifacts

- Phase 2 daily-ET comparison: run
  `python3 scripts/build_manuscript_artifacts.py --phase2 docs/results/phase2_openet_value.json --out <empty-directory>`
  and compare the output with `docs/results/`. The input record identifies a
  historical report until independent reproduction is complete.
- Idaho ETo hindcast: run
  `python3 scripts/build_manuscript_artifacts.py --eto-hindcast docs/results/idaho_eto_hindcast.json --out <empty-directory>`.
  The command rejects an incomplete hindcast result. It writes the ETo tables,
  figures, and results page from the checksum-bound result record.
- Idaho outlook candidate map: `python3 -m mlet publish-outlook --run OUTPUT_ROOT/RUN_ID`
  (always exits 1 by contract — the output is a research candidate)
- Residual-model experiment: `python3 -m mlet evaluate-outlook-residual --cases examples/outlook/residual_model_evidence.json --out <path>`
- Reference-ET cross-check: `python3 -m mlet qc-eto --member-json <path>`
  (exits 0 when the ASCE paths agree exactly and PT/ASCE-PM is inside the
  documented 0.60-1.05 band)
- Overlap consistency: `python3 -m mlet qc-overlap --window-json <path>`
  (exit 0 only when the verdict is `consistent`)
