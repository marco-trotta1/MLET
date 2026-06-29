# MLETP1

## Summary

MLET Phase 1 is an ET-only local Python scaffold. It should validate real daily
ET time-series data before any model training exists.

The core project framing is:

- predict future ET from past ET and supporting field signals;
- treat historical OpenET ET as the primary input signal;
- support ETo and NDVI as optional supporting signals;
- support measured ET as optional validation data when available;
- avoid synthetic training data;
- avoid training, model scoring, web UI, Helios integration, and irrigation logic
  in this phase.

This phase should give the project a clean data contract, a runnable CLI, and
tests. It should not make scientific claims yet.

## Status

Design, implementation plan, engineering review, and a grilling pass are complete
and approved. The detailed step-by-step build is in
`docs/superpowers/plans/2026-06-28-mlet-phase1-et-csv-validator.md`; the design
contract is in `docs/superpowers/specs/2026-06-28-mlet-phase1-et-csv-validator-design.md`.
This document is the high-level plan and reflects every decision made during
brainstorming, engineering review, and grilling. Next step: implementation.

## Assumptions

- Meetpal wants the simplest possible first version.
- MLET starts as local Python only, standard library only (no pandas/numpy yet).
- OpenET is a major input, not a minor feature.
- Past ET history initially means historical OpenET ET values.
- Measured ET is useful when available, but it is not required for the first
  scaffold to validate files.
- A file with no measured ET should validate structurally but report that it has
  no measured-ET labels (presence, not training-readiness).

## Decisions

These were confirmed during brainstorming, engineering review, and a grilling pass:

- **Dependencies:** pure standard library (`csv`, `datetime`, `argparse`,
  `dataclasses`, `math`). Zero third-party install dependencies. pandas/numpy
  arrive in later modeling phases.
- **Format role:** the contract is an **interchange/validation format** that sits
  between raw source exports (OpenET, flux towers) and pyfao56's internal model —
  it matches neither directly (`eto_mm` maps to pyfao56 `ETref`). An
  **adapter/normalization layer** is the planned next piece; the validator stays
  simple and adaptable.
- **Validation-only, clean seam:** Phase 1 validates; it does not build a loader
  or record types. The row read/parse lives in one internal helper (`_read_rows`)
  and `schema.py` is the single source of truth, so the future adapter reuses the
  parse without a rewrite.
- **Validation strictness (Phase 1):** structure + type + finiteness + physical
  validity + duplicate `(site_id, date)`. Physical-impossibility bounds
  (`ET >= 0`, `NDVI in [-1, 1]`) are **hard errors**; agronomic plausibility
  ranges stay deferred as future non-fatal warnings.
- **Sentinels by physics:** the physical bounds catch the common negative nodata
  fills (e.g. `-9999`) without a guessed sentinel list. A *positive* ET sentinel
  (`9999`) is a known, documented gap (no upper ET ceiling yet); the adapter
  normalizes source fills to blank meanwhile.
- **Labels:** the report carries `has_measured_labels` (presence), not
  `label_ready` — one stray label is not training-readiness, and Phase 1 makes no
  such claim. A coverage-gated `label_ready` returns in a later phase.
- **Temporal density:** the report includes per-site density (calendar-day span
  vs row count), non-fatal — surfaces gappy series without rejecting them.
- **Provenance / latency:** deferred but **reserved** as the named first schema
  extension (an `as_of` / `source` field, à la pyfao56's Measured/Predicted
  flag); introduced when assimilation work begins.
- **CLI surface / output:** single-file CLI and human-readable text for Phase 1;
  batch and `--json` are deferred (the report is a structured object, so `--json`
  is a trivial later add).
- **Packaging:** top-level PEP 621 `pyproject.toml` (setuptools, src layout,
  `requires-python = ">=3.9"`), a `mlet` console script, and pytest config.
- **CLI exit codes:** `0` valid, `1` invalid content, `2` usage or I/O error.

Resolved ambiguities:

- **`openet_et_mm` "required":** the *column* must exist in the header.
  Individual *values* may be blank; blanks are allowed but counted against the
  reported OpenET completeness. Any non-blank value must parse as a finite,
  physically-valid (`>= 0`) number. This keeps "OpenET completeness" a
  meaningful, honest metric.
- **Date format:** strict ISO `YYYY-MM-DD`, parsed with
  `datetime.strptime(value, "%Y-%m-%d")`. Anything else fails with row context.
- **Encoding:** files are read with `encoding="utf-8-sig"` so an Excel-exported
  UTF-8 BOM is stripped transparently; without it a file that visibly has a
  `date` column fails with a misleading "missing required column: date".
- **Ragged rows:** intentionally lenient — a row with too few columns has its
  missing trailing cells read as blank rather than erroring.

## Proposed CSV Contract

The first CSV contract is daily and site-keyed:

```csv
date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm
2024-06-01,field_001,5.2,5.8,0.71,
2024-06-02,field_001,5.5,6.1,0.73,
```

Column policy:

- `date`: required daily date, strict ISO `YYYY-MM-DD`.
- `site_id`: required field, site, tower, or location identifier.
- `openet_et_mm`: required column; values may be blank (blanks count against
  OpenET completeness), and any non-blank value must be a finite number `>= 0`
  in millimeters.
- `eto_mm`: optional reference ET (mm), `>= 0`. Maps to pyfao56 `ETref`.
- `ndvi`: optional vegetation index, mathematically bounded to `[-1, 1]`.
- `measured_et_mm`: optional independent measured ET label (mm), `>= 0`.

The validator should reject duplicate `site_id` plus `date` rows because future
time-series feature generation needs one value per site per day.

Files are read as UTF-8 with BOM tolerance (`utf-8-sig`) so spreadsheet exports
validate without surprises. Source-specific nodata fills (e.g. `-9999`) are the
adapter's job to normalize to blank before a file reaches this contract; negative
fills are also caught directly as physical-validity errors.

## Phase 1 Implementation

Add a small Python package with zero install dependencies:

- `pyproject.toml` for project metadata, console script, and pytest config.
- `src/mlet/__init__.py` exposing `__version__`.
- `src/mlet/schema.py` for the column contract constants, the non-negative /
  NDVI-bound sets, and date format (the single source of truth).
- `src/mlet/validator.py` for the `_read_rows` parse seam and
  `validate_csv(path) -> ValidationResult`.
- `src/mlet/report.py` for the `ValidationResult` / `ValidationReport` /
  `SiteSummary` (per-site span/density) dataclasses and human-readable text
  rendering.
- `src/mlet/cli.py` for the argparse entrypoint and exit-code mapping.
- `src/mlet/__main__.py` so `python -m mlet` and the console script share a path.
- `examples/et_timeseries_template.csv` as a template only, not training data.
- `tests/` for validator and CLI coverage.

The validator returns a result object rather than raising for bad data
(reporting validity is its job); it raises only on genuine I/O failure, which the
CLI catches and maps to exit code `2`.

Public commands:

```bash
mlet validate-csv examples/et_timeseries_template.csv
python -m mlet validate-csv path/to/et_timeseries.csv
```

Validation report should include:

- row count;
- site count;
- date range and temporal density by site (calendar-day span vs row count);
- OpenET completeness;
- ETo availability;
- NDVI availability;
- measured ET availability;
- `has_measured_labels=true` only when usable `measured_et_mm` values exist.

Invalid files print named, row-referenced errors and exit nonzero. To avoid
flooding the terminal on a badly-formed file, the CLI caps how many errors it
prints and notes how many more were found.

## Data Flow

```text
Daily ET CSV
  |
  v
CSV reader (stdlib csv, utf-8-sig)
  |
  v
Schema + value validation
  |
  +--> I/O error (file missing/unreadable) -> exit 2
  |
  +--> invalid structure/type/finiteness/physical/duplicate -> exit 1
  |
  +--> valid time series
          |
          v
    validation report -> stdout -> exit 0
      - row count
      - site count
      - date range + temporal density by site
      - OpenET completeness
      - ETo/NDVI availability
      - measured ET availability
      - has_measured_labels true/false
```

## Test Plan

Use pytest. Cover every branch in the scaffold. Thirty-five tests total.

Required tests:

- valid OpenET-history template succeeds and reports `has_measured_labels=false`;
- valid file with measured ET succeeds and reports `has_measured_labels=true`;
- missing `date`, `site_id`, or `openet_et_mm` fails with named missing columns;
- non-numeric `openet_et_mm`, `eto_mm`, `ndvi`, or `measured_et_mm` fails with
  row context;
- non-finite numeric values (`nan`, `inf`) fail with row context;
- negative ET / `-9999` nodata sentinel fails (`>= 0`);
- NDVI outside `[-1, 1]` fails;
- a positive ET sentinel (`9999`) currently validates (documents the known gap);
- a UTF-8 BOM on the header is handled (file still validates);
- a blank `openet_et_mm` value validates but lowers OpenET completeness;
- empty file fails clearly;
- header-only CSV fails as no usable time-series rows;
- duplicate `site_id` plus `date` rows fail;
- invalid date format fails with row context;
- report stats (counts, per-site date range, completeness/availability) and
  per-site temporal density (gappy site → span > rows) are computed correctly;
- the CLI returns 0/1/2 for valid/invalid/usage-or-IO cases;
- the CLI caps a long error list and notes how many more were found;
- `python -m mlet validate-csv ...` and `mlet validate-csv ...` exercise the
  same validator path.

Coverage target:

```text
CODE PATHS                                  TESTS
mlet.cli.main()
  |-- missing argument                      pytest CLI failure (exit 2)
  |-- file not found                        pytest CLI failure (exit 2)
  |-- valid / invalid file                  pytest CLI (exit 0 / 1)
  |-- error-display cap                      pytest CLI
  `-- validate_csv()
      |-- empty/header-only file            pytest unit
      |-- missing required headers          pytest unit
      |-- bad numeric values                pytest unit
      |-- non-finite values (nan/inf)       pytest unit
      |-- physical bounds (ET>=0, NDVI)     pytest unit
      |-- negative -9999 sentinel           pytest unit
      |-- positive 9999 sentinel (gap)      pytest unit
      |-- bad dates                         pytest unit
      |-- duplicate site/date               pytest unit
      |-- UTF-8 BOM header                  pytest unit
      |-- blank OpenET -> completeness      pytest unit
      |-- per-site temporal density         pytest unit
      |-- OpenET-only history               pytest unit
      `-- measured ET available             pytest unit
```

Verification commands:

```bash
python3 -m compileall -q src tests
python3 -m pytest            # 35 passed
mlet validate-csv examples/et_timeseries_template.csv
```

## Not In Scope

- Training models.
- Synthetic training data.
- Forecast-window generation.
- OpenET API integration.
- Web app or interactive webpage.
- Helios integration.
- Soil-water deficit or irrigation timing.
- Manuscript results or claims.
- Agronomic range checks (typical NDVI ranges, future dates) and an upper ET
  corruption ceiling (to catch positive sentinels like `9999`); deferred as
  future non-fatal warnings. (Physical bounds ET >= 0 and NDVI in [-1, 1] *are*
  in scope as hard errors.)
- Provenance / latency field (`as_of` / `source`, à la pyfao56 `MorP`); reserved
  as the named first schema extension.
- Canonical loader / typed record types; Phase 1 ships only the `_read_rows`
  parse seam.
- Batch / multi-file CLI, `--json` output, `--na-value` declaration; single-file
  text output for Phase 1.
- Ragged-row rejection; intentionally lenient for now.
- Alternate delimiters (`;`), alternate date formats.
- Streaming / chunked reading of very large files.
- pandas / numpy; deferred to modeling phases.

## What Already Exists

- `vendor/pyfao56` exists and compiles.
- `README.md` documents the broader MLET/FAO-56/soil-moisture direction.
- No MLET-owned package, CSV schema, CLI, tests, or ET time-series validator
  exists yet.

## Success Criteria

Phase 1 is successful when:

- the repo installs locally as a small, zero-dependency Python package;
- a user can run one command to validate an ET time-series CSV;
- invalid CSVs fail with clear, row-referenced messages and a nonzero exit code;
- valid OpenET-history files pass and report `has_measured_labels=false` without
  pretending they are training-ready;
- measured ET availability and per-site temporal density are reported honestly;
- spreadsheet exports (UTF-8 BOM), junk numerics (nan/inf), and physically
  impossible values / negative nodata sentinels (`-9999`) are handled;
- all validator and CLI branches have tests;
- no synthetic data is used for training.
