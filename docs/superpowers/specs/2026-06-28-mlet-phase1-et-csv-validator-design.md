# MLET Phase 1 — ET time-series CSV validator (design)

Date: 2026-06-28
Status: Approved; reviewed (engineering + grilling passes); ready to implement
Source plan: `MLETP1.md`

## Purpose

Build the first MLET-owned Python scaffold: a local, zero-dependency tool that
validates daily, site-keyed evapotranspiration (ET) time-series CSV files
**before** any model training exists. The tool establishes a clean data
contract, a runnable CLI, and tests. It makes no scientific claims and does not
train, score, serve, or ingest from external APIs.

This phase succeeds when the repo installs as a small Python package, one
command validates an ET time-series CSV, invalid CSVs fail with clear messages,
valid OpenET-history files pass without pretending to be training-ready, and
measured-ET availability is reported honestly — all covered by tests.

## Scope

### In scope
- CSV schema constants and a structural/type validator.
- A human-readable validation report.
- A CLI with a `validate-csv` subcommand, runnable as both `mlet validate-csv`
  and `python -m mlet validate-csv`.
- An OpenET-only example template (not training data).
- pytest coverage of every validator and CLI branch.

### Not in scope (Phase 1)
- Model training, scoring, or synthetic training data.
- Forecast-window / feature generation.
- OpenET (or any) API integration.
- Web app, dashboard, or interactive UI.
- Helios integration, soil-water deficit, or irrigation logic.
- Manuscript results or scientific claims.
- Agronomic range checks (typical NDVI ranges, sane ET ceilings, future dates)
  and an upper ET corruption ceiling (to catch positive sentinels like `9999`).
  Deferred; may later be added as **non-fatal warnings**. (Physical-impossibility
  bounds — ET ≥ 0, NDVI ∈ [-1, 1] — **are** in scope as hard errors; see Decisions.)
- Provenance / latency field (`as_of` / `source`, à la pyfao56 `MorP`). Reserved
  as the named first schema extension; introduced when assimilation work begins.
- Canonical loader / typed record types. Phase 1 ships only the internal
  `_read_rows` parse seam; the loader is built when the adapter/modeling phase
  has a real consumer.
- Batch / multi-file CLI, `--json` output, `--na-value` declaration, alternate
  delimiters. Deferred — Phase 1 is single-file, text output, comma CSV.

## Decisions

These were confirmed with the project owner before implementation:

1. **Dependencies:** pure Python standard library only (`csv`, `datetime`,
   `argparse`, `math`). No third-party install dependencies. pandas/numpy are
   deferred to later phases when modeling begins.
2. **Validation strictness (Phase 1):** structure + type + finiteness + physical
   validity + duplicate detection. Physical-impossibility bounds (`ET ≥ 0`,
   `NDVI ∈ [-1, 1]`) are hard errors; agronomic plausibility ranges remain out of
   scope.
3. **Packaging:** top-level PEP 621 `pyproject.toml` (not the older `setup.cfg`
   style used by the vendored `pyfao56`), because the plan calls for
   `pyproject.toml` to hold metadata, the console script, and pytest config.
4. **Format role:** the contract is an **interchange/validation format** between
   raw source exports (OpenET, flux) and pyfao56's internal model — it matches
   neither directly (`eto_mm` ⇄ pyfao56 `ETref`). An **adapter/normalization
   layer** is the planned next piece; the validator stays simple.
5. **Validation-only with a clean seam:** Phase 1 validates; it does not build a
   loader or record types. The row read/parse lives in one internal helper
   (`_read_rows`) and `schema.py` is the single source of truth, so the future
   adapter reuses the parse without a rewrite.
6. **Encoding:** read with `encoding="utf-8-sig"` so an Excel-exported BOM is
   stripped (a BOM is not whitespace and would otherwise corrupt the first
   header name).
7. **Labels:** the report carries `has_measured_labels` (presence), not
   `label_ready` — a single stray label is not training-readiness, and the
   project principle is to make no such claim. A coverage-gated `label_ready`
   returns in a later phase.
8. **Temporal density:** the report includes per-site density (calendar-day span
   vs row count), non-fatal — surfaces gappy series without rejecting them.
9. **CLI surface / output:** single-file CLI and human-readable text for Phase 1.
   Batch and `--json` are thin, non-churning additions deferred until needed.

### Resolved ambiguities
- **`openet_et_mm` "required":** the *column* is required to exist in the
  header. Individual *values* may be blank; blanks are permitted but counted
  against the reported "OpenET completeness" metric. Any non-blank value must be
  numeric and finite. This keeps "OpenET completeness" a meaningful metric and
  matches the project's "report honestly" principle.
- **Date format:** strict ISO `YYYY-MM-DD` only, matching the template. Parsed
  with `datetime.strptime(value, "%Y-%m-%d")` for version-independent
  strictness. Any other format fails with row context.
- **Nodata sentinels:** caught by physics, not a guessed list — a `-9999` ET
  trips `ET ≥ 0` and a `-9999`/`9999` NDVI trips `[-1, 1]`. A *positive* ET
  sentinel (`9999`) is a known, documented gap (no upper ET ceiling yet); the
  adapter normalizes source fills to blank meanwhile.

## CSV contract

Daily, site-keyed. One row per `(site_id, date)`.

```csv
date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm
2024-06-01,field_001,5.2,5.8,0.71,
2024-06-02,field_001,5.5,6.1,0.73,
```

| Column           | Required | Type            | Notes                                            |
| ---------------- | -------- | --------------- | ------------------------------------------------ |
| `date`           | yes      | `YYYY-MM-DD`    | Daily date.                                       |
| `site_id`        | yes      | string          | Field/site/tower/location identifier.            |
| `openet_et_mm`   | yes (col)| number ≥ 0 or blank | Historical OpenET ET (mm). Blanks reduce completeness; non-blank must be finite and ≥ 0. |
| `eto_mm`         | no       | number ≥ 0 or blank | Reference ET (mm). Maps to pyfao56 `ETref`.       |
| `ndvi`           | no       | number ∈ [-1, 1] or blank | Vegetation index (mathematically bounded).  |
| `measured_et_mm` | no       | number ≥ 0 or blank | Independent measured ET label.                    |

Source-specific nodata fill values (e.g. `-9999`) must already be normalized to
blank by the adapter before a file reaches this contract; negative fills are also
caught as physical-validity errors.

## Architecture

Four small, single-purpose modules under `src/mlet/`, mirroring the plan's
concerns (schema / validation / reporting / CLI). Each has one clear job and a
narrow interface.

```
pyproject.toml                          # PEP 621 metadata, console script, pytest config
src/mlet/__init__.py                    # __version__ = "0.1.0"
src/mlet/__main__.py                    # enables `python -m mlet ...`
src/mlet/schema.py                      # column names, required/numeric/non-negative sets, NDVI bounds, DATE_FORMAT
src/mlet/validator.py                   # _read_rows seam + validate_csv(path) -> ValidationResult
src/mlet/report.py                      # ValidationResult + ValidationReport + SiteSummary dataclasses + text rendering
src/mlet/cli.py                         # argparse, main(argv) -> exit code
examples/et_timeseries_template.csv     # OpenET-only template (no measured ET)
tests/test_validator.py                 # unit coverage of every validator branch
tests/test_cli.py                       # CLI exit codes + both invocation paths
```

`vendor/pyfao56/` is untouched. The top-level package declares zero install
dependencies and does not import `pyfao56`.

### Module responsibilities

- **`schema.py`** — the data contract as constants: column names,
  `REQUIRED_COLUMNS`, `NUMERIC_COLUMNS`, `NONNEGATIVE_COLUMNS`, `NDVI_MIN`/
  `NDVI_MAX`, `ALL_COLUMNS`, and `DATE_FORMAT = "%Y-%m-%d"`. The single source of
  truth the validator and the future adapter both import. No logic.
- **`validator.py`** — `_read_rows(path)` (the shared parse seam: open with
  `utf-8-sig`, headerize, return data rows) plus
  `validate_csv(path) -> ValidationResult`. Accumulates errors (structure, type,
  finiteness, physical bounds, duplicates) and, when valid, computes a
  `ValidationReport` including per-site `span_days`. Raises only on I/O failure.
- **`report.py`** — `ValidationResult` (is_valid, errors, report),
  `ValidationReport` (stats + `has_measured_labels`), and `SiteSummary`
  (per-site span/density) dataclasses, plus a `to_text()` renderer. Keeping the
  report as structured data makes a future `--json` flag trivial.
- **`cli.py`** — `main(argv=None) -> int`. argparse with a `validate-csv`
  subcommand taking a path. Catches I/O errors, prints results, returns the
  exit code.
- **`__main__.py`** — `raise SystemExit(main())` so `python -m mlet` and the
  `mlet` console script share one code path.

## Error model

`validate_csv()` **returns** a result; it does not raise for bad data.
Reporting validity is the tool's job, so "invalid content" is a normal outcome.
The validator accumulates errors (e.g. all missing columns; bad rows up to a
display cap) rather than stopping at the first. Genuine I/O problems (missing or
unreadable file) raise and are caught by the CLI.

### CLI exit codes
- `0` — file is valid; report printed to stdout.
- `1` — file is structurally invalid (missing columns, bad numeric/date values,
  duplicate `(site_id, date)`, empty/header-only); errors printed to stderr.
- `2` — usage or I/O error (missing CLI argument → argparse default;
  file-not-found mapped here too).

## Validation algorithm

1. **Open the file.** If it does not exist / is unreadable → raise I/O error
   (CLI → exit 2).
2. **Empty file** (no header line) → invalid: `"file is empty"`.
3. **Required columns** (`date`, `site_id`, `openet_et_mm`) — any missing from
   the header → invalid, listing **all** missing names. Stop (rows can't be
   validated without them).
4. **Header but zero data rows** → invalid: `"no usable time-series rows"`.
5. **Per data row** (1-based row numbers, header = row 1):
   - `date` parses as strict `YYYY-MM-DD`, else error with row context.
   - Each numeric column, if non-blank, must parse as a float, be finite
     (`nan`/`inf` rejected), and satisfy physical validity: ET columns
     (`openet_et_mm`, `eto_mm`, `measured_et_mm`) `≥ 0`; `ndvi` ∈ `[-1, 1]`.
     Blanks are allowed and counted as incomplete.
   - `(site_id, date)` must be unique; a repeat is a duplicate error with row
     context.
6. If any row/duplicate errors accumulated → invalid (display capped at the CLI,
   with a "… and N more" note when exceeded; full count retained in the result).
7. If valid → compute the report, including per-site `span_days` (from parsed
   `date` objects) for temporal density, and return it.

## Validation report (valid files)

Rendered to stdout via `ValidationReport.to_text()`:

- Row count (data rows).
- Site count.
- Per-site date range, row count, and temporal density:
  `field_001: 2024-06-01 -> 2024-06-30 (30-day span, 28 rows, 93% dense)`.
- OpenET completeness: `n/N (pct)` non-blank `openet_et_mm`.
- ETo availability: `n/N (pct)` non-blank `eto_mm`.
- NDVI availability: `n/N (pct)` non-blank `ndvi`.
- Measured-ET availability: `n/N (pct)` non-blank `measured_et_mm`.
- `has_measured_labels`: `true` **iff** at least one usable (non-blank, numeric)
  `measured_et_mm` value exists; otherwise `false`. (Presence, not training-
  readiness.)

## Data flow

```text
Daily ET CSV
  |
  v
csv reader (stdlib)
  |
  v
schema + value validation (validator.py)
  |
  +--> I/O error            -> raised -> CLI exit 2
  +--> invalid structure    -> ValidationResult(is_valid=False) -> CLI exit 1
  +--> valid time series
          |
          v
    ValidationReport -> to_text() -> stdout -> CLI exit 0
```

## Packaging

`pyproject.toml` (PEP 621), setuptools backend, src layout:

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "mlet"
version = "0.1.0"
description = "Machine Learning Evapotranspiration — Phase 1 ET time-series CSV validator"
requires-python = ">=3.9"
dependencies = []

[project.scripts]
mlet = "mlet.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

The `mlet` console script and `python -m mlet` both resolve to `cli.main`.

## Test plan

pytest, with `tmp_path` fixtures writing CSV inputs. One assertion-bearing test
per branch:

**Validator (`tests/test_validator.py`)**
- Valid OpenET-only template → valid, `has_measured_labels=false`.
- Valid file with measured ET → valid, `has_measured_labels=true`.
- Blank `openet_et_mm` value → valid, lowers OpenET completeness.
- Missing `date` / `site_id` / `openet_et_mm` → invalid, names the missing
  column(s).
- Non-numeric `openet_et_mm` / `eto_mm` / `ndvi` / `measured_et_mm` → invalid
  with row context.
- Non-finite (`nan`, `inf`) numeric → invalid with row context.
- Negative ET / `-9999` nodata sentinel → invalid (`>= 0`).
- NDVI outside `[-1, 1]` → invalid.
- Positive ET sentinel (`9999`) → currently valid (documents the known gap).
- UTF-8 BOM header → still validates.
- Empty file → invalid, clear message.
- Header-only file → invalid, "no usable time-series rows".
- Duplicate `(site_id, date)` → invalid with row context.
- Invalid date format → invalid with row context.
- Report stats (counts, per-site date range, completeness/availability) and
  per-site temporal density (gappy site → span > rows) on known small files.

**CLI (`tests/test_cli.py`)**
- `validate-csv` on the template → exit 0.
- `validate-csv` on an invalid file → exit 1.
- Long error list → capped output with a "… and N more" note.
- Missing argument → exit 2.
- File-not-found → exit 2.
- Both `mlet validate-csv …` and `python -m mlet validate-csv …` exercise the
  same validator path (same outcome on the same input).

Total: ~35 tests (6 package, 3 report, 20 validator, 6 CLI).

### Verification commands
```bash
python3 -m compileall -q src tests
python3 -m pytest
mlet validate-csv examples/et_timeseries_template.csv
```

## Success criteria

- Repo installs locally as a small Python package (`pip install -e .`).
- One command validates an ET time-series CSV.
- Invalid CSVs fail with clear, row-referenced messages and a nonzero exit code.
- Valid OpenET-history files pass and report `has_measured_labels=false`.
- Measured-ET availability and per-site temporal density are reported honestly.
- Spreadsheet exports (UTF-8 BOM) and physically-impossible values / negative
  nodata sentinels (`-9999`) are handled.
- Every validator and CLI branch is covered by a test.
- No synthetic data; no scientific claims.
