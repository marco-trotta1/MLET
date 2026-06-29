# MLET Phase 1 — ET time-series CSV validator (design)

Date: 2026-06-28
Status: Approved (design); pending implementation plan
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
- Domain-range value checks (e.g. ET ≥ 0, NDVI ∈ [-1, 1]). Deferred; may later
  be added as **non-fatal warnings**.

## Decisions

These were confirmed with the project owner before implementation:

1. **Dependencies:** pure Python standard library only (`csv`, `datetime`,
   `argparse`). No third-party install dependencies. pandas/numpy are deferred
   to later phases when modeling begins.
2. **Validation strictness (Phase 1):** structure + type + duplicate detection
   only. Domain/range plausibility checks are explicitly out of scope for now.
3. **Packaging:** top-level PEP 621 `pyproject.toml` (not the older `setup.cfg`
   style used by the vendored `pyfao56`), because the plan calls for
   `pyproject.toml` to hold metadata, the console script, and pytest config.

### Resolved ambiguities
- **`openet_et_mm` "required":** the *column* is required to exist in the
  header. Individual *values* may be blank; blanks are permitted but counted
  against the reported "OpenET completeness" metric. Any non-blank value must be
  numeric. This keeps "OpenET completeness" a meaningful metric and matches the
  project's "report honestly" principle. (If every row should instead be forced
  to carry a value, that becomes a hard-fail rule — not adopted here.)
- **Date format:** strict ISO `YYYY-MM-DD` only, matching the template. Parsed
  with `datetime.strptime(value, "%Y-%m-%d")` for version-independent
  strictness. Any other format fails with row context.

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
| `openet_et_mm`   | yes (col)| number ≥ blank  | Historical OpenET ET (mm). Blanks reduce completeness; non-blank must be numeric. |
| `eto_mm`         | no       | number or blank | Reference ET (mm).                                |
| `ndvi`           | no       | number or blank | Vegetation index.                                 |
| `measured_et_mm` | no       | number or blank | Independent measured ET label.                    |

## Architecture

Four small, single-purpose modules under `src/mlet/`, mirroring the plan's
concerns (schema / validation / reporting / CLI). Each has one clear job and a
narrow interface.

```
pyproject.toml                          # PEP 621 metadata, console script, pytest config
src/mlet/__init__.py                    # __version__ = "0.1.0"
src/mlet/__main__.py                    # enables `python -m mlet ...`
src/mlet/schema.py                      # column names, required/optional sets, DATE_FORMAT
src/mlet/validator.py                   # validate_csv(path) -> ValidationResult
src/mlet/report.py                      # ValidationResult + ValidationReport dataclasses + text rendering
src/mlet/cli.py                         # argparse, main(argv) -> exit code
examples/et_timeseries_template.csv     # OpenET-only template (no measured ET)
tests/test_validator.py                 # unit coverage of every validator branch
tests/test_cli.py                       # CLI exit codes + both invocation paths
```

`vendor/pyfao56/` is untouched. The top-level package declares zero install
dependencies and does not import `pyfao56`.

### Module responsibilities

- **`schema.py`** — the data contract as constants: `DATE_COLUMN`,
  `SITE_COLUMN`, required column list, optional numeric column list, the full
  ordered column list, and `DATE_FORMAT = "%Y-%m-%d"`. No logic.
- **`validator.py`** — `validate_csv(path) -> ValidationResult`. Reads the CSV
  with the stdlib `csv` module, accumulates errors, and (when valid) computes a
  `ValidationReport`. Raises only on I/O failure (e.g. file unreadable); the
  caller handles that.
- **`report.py`** — `ValidationResult` (is_valid, errors, report) and
  `ValidationReport` (the stats) dataclasses, plus a `to_text()` renderer.
  Keeping the report as structured data makes a future `--json` flag trivial.
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
   - `openet_et_mm`: if non-blank, must be numeric (blank allowed, counted as
     incomplete).
   - `eto_mm`, `ndvi`, `measured_et_mm`: if non-blank, must be numeric.
   - `(site_id, date)` must be unique; a repeat is a duplicate error with row
     context.
6. If any row/duplicate errors accumulated → invalid (display capped, with a
   "… and N more" note when exceeded; full count retained in the result).
7. If valid → compute and return the report.

## Validation report (valid files)

Rendered to stdout via `ValidationReport.to_text()`:

- Row count (data rows).
- Site count.
- Per-site date range and row count: `field_001: 2024-06-01 → 2024-06-30 (30 rows)`.
- OpenET completeness: `n/N (pct)` non-blank `openet_et_mm`.
- ETo availability: `n/N (pct)` non-blank `eto_mm`.
- NDVI availability: `n/N (pct)` non-blank `ndvi`.
- Measured-ET availability: `n/N (pct)` non-blank `measured_et_mm`.
- `label_ready`: `true` **iff** at least one usable (non-blank, numeric)
  `measured_et_mm` value exists; otherwise `false`.

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
- Valid OpenET-only template → valid, `label_ready=false`.
- Valid file with measured ET → valid, `label_ready=true`.
- Missing `date` / `site_id` / `openet_et_mm` → invalid, names the missing
  column(s).
- Non-numeric `openet_et_mm` / `eto_mm` / `ndvi` / `measured_et_mm` → invalid
  with row context.
- Empty file → invalid, clear message.
- Header-only file → invalid, "no usable time-series rows".
- Duplicate `(site_id, date)` → invalid with row context.
- Invalid date format → invalid with row context.
- Report stats (row/site counts, per-site date range, completeness/availability)
  on a known small file.

**CLI (`tests/test_cli.py`)**
- `validate-csv` on the template → exit 0.
- `validate-csv` on an invalid file → exit 1.
- Missing argument → exit 2.
- File-not-found → exit 2.
- Both `mlet validate-csv …` and `python -m mlet validate-csv …` exercise the
  same validator path (same outcome on the same input).

### Verification commands
```bash
python3 -m compileall -q src tests
python3 -m pytest
mlet validate-csv examples/et_timeseries_template.csv
```

## Success criteria

- Repo installs locally as a small Python package (`pip install -e .`).
- One command validates an ET time-series CSV.
- Invalid CSVs fail with clear, named messages and a nonzero exit code.
- Valid OpenET-history files pass and report `label_ready=false`.
- Measured-ET availability is reported honestly.
- Every validator and CLI branch is covered by a test.
- No synthetic data; no scientific claims.
