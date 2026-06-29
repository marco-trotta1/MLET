# MLET Phase 1 — ET time-series CSV validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a local, zero-dependency Python package that validates daily, site-keyed ET time-series CSV files and reports their contents honestly, with a `mlet validate-csv` CLI and full test coverage.

**Architecture:** Four small single-purpose modules under `src/mlet/` (`schema` → contract constants, `validator` → `validate_csv()`, `report` → result/report dataclasses + text rendering, `cli` → argparse entrypoint). The validator reads with the stdlib `csv` module, accumulates errors, and returns a `ValidationResult` rather than raising for bad data. The CLI maps results to exit codes.

**Tech Stack:** Python 3.9+ standard library only (`csv`, `datetime`, `argparse`, `dataclasses`). Packaging via PEP 621 `pyproject.toml` + setuptools, src layout. Tests via pytest.

## Global Constraints

- **Dependencies:** zero third-party install dependencies; standard library only.
- **Python floor:** `requires-python = ">=3.9"`.
- **Packaging:** top-level PEP 621 `pyproject.toml`, setuptools backend, src layout (`where = ["src"]`). Do not touch `vendor/pyfao56/`.
- **Encoding:** open files with `encoding="utf-8-sig"` so an Excel-exported UTF-8 BOM is stripped transparently (BOM is not whitespace, so it would otherwise corrupt the first header name).
- **Date format:** strict ISO `YYYY-MM-DD`, parsed with `datetime.strptime(value, "%Y-%m-%d")`.
- **`openet_et_mm` rule:** the column must exist; individual values may be blank (counted against "OpenET completeness"); any non-blank value must parse as a float.
- **Numeric values:** non-blank numeric cells must parse as a float AND be finite — `nan`/`inf`/`-inf` are rejected with row context (they are never valid ET data).
- **Physical validity:** ET columns (`openet_et_mm`, `eto_mm`, `measured_et_mm`) must be `>= 0`; `ndvi` must be in `[-1, 1]`. Violations are hard errors — this catches negative nodata sentinels (e.g. `-9999`) by physics, not by a guessed sentinel list. Positive ET sentinels (e.g. `9999`) and agronomic plausibility ranges are deferred.
- **Strictness (Phase 1):** structure + type + finiteness + physical validity + duplicate `(site_id, date)`. No agronomic range checks yet. Ragged rows (wrong column count) stay lenient: missing trailing cells read as blank.
- **Labels:** the report carries a presence flag `has_measured_labels` (true iff any usable `measured_et_mm` value exists). A coverage-gated `label_ready` is deferred to a later phase.
- **Temporal density:** the report includes per-site density (calendar-day span vs row count), non-fatal — surfaces gappy series without rejecting them.
- **Format role:** the contract is an interchange/validation format sitting between raw source exports and pyfao56's internal model (`eto_mm` maps to pyfao56 `ETref`). An adapter/normalization layer and a provenance/latency field (à la pyfao56 `MorP`) are the planned next extensions, not Phase 1. `validate_csv` shares a `_read_rows` seam and uses `schema.py` as the single source of truth so the future adapter can reuse the parse.
- **CLI exit codes:** `0` valid · `1` invalid content · `2` usage/IO error.
- **Style:** stdlib idioms, 4-space indent, double-quoted strings, `from __future__ import annotations` at the top of modules using PEP 585/604 annotations.

---

### Task 1: Package scaffold + schema contract

**Files:**
- Create: `pyproject.toml`
- Create: `src/mlet/__init__.py`
- Create: `src/mlet/schema.py`
- Test: `tests/test_package.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `mlet.__version__: str`
  - `mlet.schema` constants: `DATE_COLUMN`, `SITE_COLUMN`, `OPENET_COLUMN`, `ETO_COLUMN`, `NDVI_COLUMN`, `MEASURED_COLUMN` (all `str`); `REQUIRED_COLUMNS: tuple[str, ...]` = `("date", "site_id", "openet_et_mm")`; `NUMERIC_COLUMNS: tuple[str, ...]` = `("openet_et_mm", "eto_mm", "ndvi", "measured_et_mm")`; `NONNEGATIVE_COLUMNS: tuple[str, ...]` = `("openet_et_mm", "eto_mm", "measured_et_mm")`; `NDVI_MIN: float` = `-1.0`; `NDVI_MAX: float` = `1.0`; `ALL_COLUMNS: tuple[str, ...]` (full ordered header); `DATE_FORMAT: str` = `"%Y-%m-%d"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_package.py`:

```python
import mlet
from mlet import schema


def test_version_is_a_string():
    assert isinstance(mlet.__version__, str)
    assert mlet.__version__


def test_required_columns_contract():
    assert schema.REQUIRED_COLUMNS == ("date", "site_id", "openet_et_mm")


def test_numeric_columns_contract():
    assert schema.NUMERIC_COLUMNS == (
        "openet_et_mm",
        "eto_mm",
        "ndvi",
        "measured_et_mm",
    )


def test_all_columns_order():
    assert schema.ALL_COLUMNS == (
        "date",
        "site_id",
        "openet_et_mm",
        "eto_mm",
        "ndvi",
        "measured_et_mm",
    )


def test_date_format_is_strict_iso():
    assert schema.DATE_FORMAT == "%Y-%m-%d"


def test_physical_bounds_contract():
    assert schema.NONNEGATIVE_COLUMNS == ("openet_et_mm", "eto_mm", "measured_et_mm")
    assert (schema.NDVI_MIN, schema.NDVI_MAX) == (-1.0, 1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_package.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlet'`.

- [ ] **Step 3: Create the package files**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "mlet"
version = "0.1.0"
description = "Machine Learning Evapotranspiration — Phase 1 ET time-series CSV validator"
readme = "README.md"
requires-python = ">=3.9"
dependencies = []

[project.scripts]
mlet = "mlet.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `src/mlet/__init__.py`:

```python
"""MLET — Machine Learning Evapotranspiration (Phase 1 scaffold)."""

__version__ = "0.1.0"
```

Create `src/mlet/schema.py`:

```python
"""Column contract for MLET ET time-series CSV files."""

DATE_COLUMN = "date"
SITE_COLUMN = "site_id"
OPENET_COLUMN = "openet_et_mm"
ETO_COLUMN = "eto_mm"
NDVI_COLUMN = "ndvi"
MEASURED_COLUMN = "measured_et_mm"

# Columns that must be present in the header.
REQUIRED_COLUMNS = (DATE_COLUMN, SITE_COLUMN, OPENET_COLUMN)

# Columns whose non-blank values must parse as floats.
NUMERIC_COLUMNS = (OPENET_COLUMN, ETO_COLUMN, NDVI_COLUMN, MEASURED_COLUMN)

# ET columns (mm) are physically non-negative.
NONNEGATIVE_COLUMNS = (OPENET_COLUMN, ETO_COLUMN, MEASURED_COLUMN)

# NDVI is a normalized ratio, mathematically bounded to [-1, 1].
NDVI_MIN = -1.0
NDVI_MAX = 1.0

# Full ordered contract, used for the example template.
ALL_COLUMNS = (
    DATE_COLUMN,
    SITE_COLUMN,
    OPENET_COLUMN,
    ETO_COLUMN,
    NDVI_COLUMN,
    MEASURED_COLUMN,
)

# Strict ISO date format (YYYY-MM-DD).
DATE_FORMAT = "%Y-%m-%d"
```

- [ ] **Step 4: Install the package editable**

Run: `python3 -m pip install -e .`
Expected: `Successfully installed mlet-0.1.0`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_package.py -q`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/mlet/__init__.py src/mlet/schema.py tests/test_package.py
git commit -m "feat(mlet): scaffold package and ET CSV schema contract"
```

---

### Task 2: Result and report types with text rendering

**Files:**
- Create: `src/mlet/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: nothing (pure dataclasses).
- Produces:
  - `SiteSummary(site_id: str, row_count: int, first_date: str, last_date: str, span_days: int)`
  - `ValidationReport(row_count: int, site_count: int, sites: list[SiteSummary], openet_present: int, eto_present: int, ndvi_present: int, measured_present: int, has_measured_labels: bool)` with method `to_text() -> str`. The per-site line reports temporal density (span vs rows).
  - `ValidationResult(is_valid: bool, errors: list[str] = [], report: ValidationReport | None = None)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:

```python
from mlet.report import SiteSummary, ValidationReport, ValidationResult


def make_report():
    return ValidationReport(
        row_count=2,
        site_count=1,
        sites=[SiteSummary("field_001", 2, "2024-06-01", "2024-06-02", span_days=2)],
        openet_present=2,
        eto_present=2,
        ndvi_present=2,
        measured_present=0,
        has_measured_labels=False,
    )


def test_report_to_text_contains_key_lines():
    text = make_report().to_text()
    assert "rows: 2" in text
    assert "sites: 1" in text
    assert "field_001: 2024-06-01 -> 2024-06-02 (2-day span, 2 rows, 100% dense)" in text
    assert "OpenET completeness: 2/2 (100.0%)" in text
    assert "ETo availability: 2/2 (100.0%)" in text
    assert "measured ET availability: 0/2 (0.0%)" in text
    assert "has_measured_labels: false" in text


def test_ratio_handles_zero_rows():
    report = ValidationReport(
        row_count=0,
        site_count=0,
        sites=[],
        openet_present=0,
        eto_present=0,
        ndvi_present=0,
        measured_present=0,
        has_measured_labels=False,
    )
    assert "OpenET completeness: 0/0 (0.0%)" in report.to_text()


def test_result_defaults():
    result = ValidationResult(is_valid=True)
    assert result.errors == []
    assert result.report is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_report.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlet.report'`.

- [ ] **Step 3: Implement `report.py`**

Create `src/mlet/report.py`:

```python
"""Result and report types for ET CSV validation, plus text rendering."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SiteSummary:
    site_id: str
    row_count: int
    first_date: str
    last_date: str
    span_days: int


@dataclass
class ValidationReport:
    row_count: int
    site_count: int
    sites: list[SiteSummary]
    openet_present: int
    eto_present: int
    ndvi_present: int
    measured_present: int
    has_measured_labels: bool

    def to_text(self) -> str:
        lines = [
            f"rows: {self.row_count}",
            f"sites: {self.site_count}",
        ]
        for s in self.sites:
            density = (s.row_count / s.span_days * 100) if s.span_days else 0.0
            lines.append(
                f"  {s.site_id}: {s.first_date} -> {s.last_date} "
                f"({s.span_days}-day span, {s.row_count} rows, {density:.0f}% dense)"
            )
        lines.append(f"OpenET completeness: {_ratio(self.openet_present, self.row_count)}")
        lines.append(f"ETo availability: {_ratio(self.eto_present, self.row_count)}")
        lines.append(f"NDVI availability: {_ratio(self.ndvi_present, self.row_count)}")
        lines.append(
            f"measured ET availability: {_ratio(self.measured_present, self.row_count)}"
        )
        lines.append(f"has_measured_labels: {str(self.has_measured_labels).lower()}")
        return "\n".join(lines)


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    report: ValidationReport | None = None


def _ratio(present: int, total: int) -> str:
    pct = (present / total * 100) if total else 0.0
    return f"{present}/{total} ({pct:.1f}%)"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_report.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/mlet/report.py tests/test_report.py
git commit -m "feat(mlet): add validation result and report types"
```

---

### Task 3: CSV validator + example template

**Files:**
- Create: `src/mlet/validator.py`
- Create: `examples/et_timeseries_template.csv`
- Test: `tests/test_validator.py`

**Interfaces:**
- Consumes: `mlet.schema` constants (names + `NONNEGATIVE_COLUMNS` / `NDVI_MIN` / `NDVI_MAX` bounds); `mlet.report.SiteSummary`, `ValidationReport`, `ValidationResult`.
- Produces: `validate_csv(path: str | os.PathLike) -> ValidationResult`. Returns `is_valid=False` with `errors` for structural/type/finiteness/physical-validity/duplicate problems; returns `is_valid=True` with a populated `report` (including per-site `span_days`) otherwise. Raises `OSError` only when the file cannot be opened. Internal `_read_rows(path)` is the shared parse seam for the future adapter.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_validator.py`:

```python
from pathlib import Path

from mlet.validator import validate_csv

HEADER = "date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm\n"
TEMPLATE = HEADER + "2024-06-01,field_001,5.2,5.8,0.71,\n2024-06-02,field_001,5.5,6.1,0.73,\n"


def write_csv(tmp_path: Path, content: str) -> str:
    p = tmp_path / "data.csv"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_valid_openet_only_template_has_no_measured_labels(tmp_path):
    result = validate_csv(write_csv(tmp_path, TEMPLATE))
    assert result.is_valid
    assert result.report.has_measured_labels is False
    assert result.report.row_count == 2
    assert result.report.site_count == 1


def test_measured_et_present_sets_has_measured_labels(tmp_path):
    content = HEADER + "2024-06-01,field_001,5.2,5.8,0.71,5.0\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    assert result.report.has_measured_labels is True
    assert result.report.measured_present == 1


def test_blank_openet_value_is_allowed_but_counted_incomplete(tmp_path):
    content = HEADER + "2024-06-01,field_001,5.2,5.8,0.71,\n2024-06-02,field_001,,6.1,0.73,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    assert result.report.openet_present == 1
    assert result.report.row_count == 2


def test_missing_required_column_fails_with_name(tmp_path):
    content = "date,site_id,eto_mm,ndvi,measured_et_mm\n2024-06-01,field_001,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("openet_et_mm" in e for e in result.errors)


def test_non_numeric_openet_fails_with_row_context(tmp_path):
    content = HEADER + "2024-06-01,field_001,abc,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("row 2" in e and "openet_et_mm" in e for e in result.errors)


def test_non_numeric_optional_columns_fail(tmp_path):
    content = HEADER + "2024-06-01,field_001,5.2,xx,yy,zz\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("eto_mm" in e for e in result.errors)
    assert any("ndvi" in e for e in result.errors)
    assert any("measured_et_mm" in e for e in result.errors)


def test_negative_et_fails(tmp_path):
    content = HEADER + "2024-06-01,field_001,-1.0,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("row 2" in e and "openet_et_mm" in e and ">= 0" in e for e in result.errors)


def test_negative_nodata_sentinel_fails(tmp_path):
    # -9999 is a common nodata fill value; it is physically impossible ET.
    content = HEADER + "2024-06-01,field_001,-9999,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any(">= 0" in e for e in result.errors)


def test_ndvi_out_of_range_fails(tmp_path):
    content = HEADER + "2024-06-01,field_001,5.2,5.8,1.5,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("row 2" in e and "ndvi" in e and "[-1, 1]" in e for e in result.errors)


def test_positive_et_sentinel_not_yet_caught(tmp_path):
    # Documents a known Phase 1 limitation: a positive nodata sentinel (e.g. 9999)
    # passes the >= 0 check. An upper ET ceiling is deferred to a later phase.
    content = HEADER + "2024-06-01,field_001,9999,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid


def test_density_reported_for_gappy_site(tmp_path):
    # Two rows spanning 10 calendar days -> 10-day span, 2 rows, 20% dense.
    content = HEADER + "2024-06-01,field_001,5.2,5.8,0.71,\n2024-06-10,field_001,5.5,6.1,0.73,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    site = result.report.sites[0]
    assert site.span_days == 10
    assert site.row_count == 2


def test_non_finite_numeric_fails(tmp_path):
    content = HEADER + "2024-06-01,field_001,nan,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("row 2" in e and "non-finite" in e and "openet_et_mm" in e for e in result.errors)


def test_inf_numeric_fails(tmp_path):
    content = HEADER + "2024-06-01,field_001,inf,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("non-finite" in e for e in result.errors)


def test_utf8_bom_header_is_handled(tmp_path):
    # Excel prepends a UTF-8 BOM; it must not become part of the first header name.
    content = "\ufeff" + HEADER + "2024-06-01,field_001,5.2,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    assert result.report.row_count == 1


def test_empty_file_fails(tmp_path):
    result = validate_csv(write_csv(tmp_path, ""))
    assert not result.is_valid
    assert any("empty" in e for e in result.errors)


def test_header_only_fails(tmp_path):
    result = validate_csv(write_csv(tmp_path, HEADER))
    assert not result.is_valid
    assert any("no usable time-series rows" in e for e in result.errors)


def test_duplicate_site_date_fails(tmp_path):
    content = HEADER + "2024-06-01,field_001,5.2,5.8,0.71,\n2024-06-01,field_001,5.3,5.9,0.72,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("duplicate" in e and "row 3" in e for e in result.errors)


def test_invalid_date_format_fails_with_row_context(tmp_path):
    content = HEADER + "06/01/2024,field_001,5.2,5.8,0.71,\n"
    result = validate_csv(write_csv(tmp_path, content))
    assert not result.is_valid
    assert any("row 2" in e and "invalid date" in e for e in result.errors)


def test_report_stats_and_date_range(tmp_path):
    content = (
        HEADER
        + "2024-06-02,field_001,5.2,5.8,0.71,\n"
        + "2024-06-01,field_001,5.5,,0.73,\n"
        + "2024-06-01,field_002,4.9,5.0,,\n"
    )
    result = validate_csv(write_csv(tmp_path, content))
    assert result.is_valid
    r = result.report
    assert r.row_count == 3
    assert r.site_count == 2
    assert r.openet_present == 3
    assert r.eto_present == 2
    assert r.ndvi_present == 2
    assert r.measured_present == 0
    by_id = {s.site_id: s for s in r.sites}
    assert by_id["field_001"].first_date == "2024-06-01"
    assert by_id["field_001"].last_date == "2024-06-02"
    assert by_id["field_001"].row_count == 2
    assert by_id["field_002"].row_count == 1


def test_shipped_template_validates_and_has_no_measured_labels():
    repo_root = Path(__file__).resolve().parents[1]
    result = validate_csv(str(repo_root / "examples" / "et_timeseries_template.csv"))
    assert result.is_valid
    assert result.report.has_measured_labels is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_validator.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlet.validator'`.

- [ ] **Step 3: Create the example template**

Create `examples/et_timeseries_template.csv`:

```csv
date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm
2024-06-01,field_001,5.2,5.8,0.71,
2024-06-02,field_001,5.5,6.1,0.73,
2024-06-03,field_001,5.1,5.6,0.74,
```

- [ ] **Step 4: Implement `validator.py`**

Create `src/mlet/validator.py`:

```python
"""Validate daily, site-keyed ET time-series CSV files."""

from __future__ import annotations

import csv
import math
from datetime import datetime

from mlet import schema
from mlet.report import SiteSummary, ValidationReport, ValidationResult


def _cell(row, header_index, name):
    """Return the stripped value for a column, or "" if the row is short."""
    i = header_index[name]
    return row[i].strip() if i < len(row) else ""


def _read_rows(path):
    """Read a CSV into (header, header_index, data_rows).

    Shared read seam: a future source adapter reuses this to parse the
    interchange format without re-implementing CSV reading. `utf-8-sig`
    transparently strips an Excel-exported BOM. Raises OSError on I/O failure.
    Returns (None, None, None) for an empty file.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        return None, None, None
    header = [c.strip() for c in rows[0]]
    header_index = {name: header.index(name) for name in header}
    return header, header_index, rows[1:]


def validate_csv(path):
    """Validate an ET time-series CSV. Returns a ValidationResult.

    Raises OSError only when the file cannot be opened.
    """
    header, header_index, data_rows = _read_rows(path)

    if header is None:
        return ValidationResult(is_valid=False, errors=["file is empty"])

    missing = [c for c in schema.REQUIRED_COLUMNS if c not in header]
    if missing:
        return ValidationResult(
            is_valid=False,
            errors=[f"missing required column(s): {', '.join(missing)}"],
        )

    if not data_rows:
        return ValidationResult(is_valid=False, errors=["no usable time-series rows"])

    errors = []
    seen_keys = set()

    site_order = []
    site_rows = {}
    site_min = {}
    site_max = {}

    openet_present = 0
    eto_present = 0
    ndvi_present = 0
    measured_present = 0

    for offset, row in enumerate(data_rows):
        line_no = offset + 2  # header is line 1

        date_val = _cell(row, header_index, schema.DATE_COLUMN)
        site_val = _cell(row, header_index, schema.SITE_COLUMN)

        parsed_date = None
        try:
            parsed_date = datetime.strptime(date_val, schema.DATE_FORMAT).date()
        except ValueError:
            errors.append(
                f"row {line_no}: invalid date {date_val!r} (expected YYYY-MM-DD)"
            )

        for name in schema.NUMERIC_COLUMNS:
            raw = _cell(row, header_index, name)
            if raw == "":
                continue
            try:
                value = float(raw)
            except ValueError:
                errors.append(f"row {line_no}: non-numeric {name} {raw!r}")
                continue
            if not math.isfinite(value):
                errors.append(f"row {line_no}: non-finite {name} {raw!r}")
                continue
            # Physical/mathematical validity. Catches negative nodata sentinels
            # (e.g. -9999) by physics rather than a guessed sentinel list.
            if name in schema.NONNEGATIVE_COLUMNS and value < 0:
                errors.append(f"row {line_no}: {name} must be >= 0, got {value}")
            elif name == schema.NDVI_COLUMN and not (
                schema.NDVI_MIN <= value <= schema.NDVI_MAX
            ):
                errors.append(f"row {line_no}: ndvi must be in [-1, 1], got {value}")

        if parsed_date is not None:
            key = (site_val, date_val)
            if key in seen_keys:
                errors.append(
                    f"row {line_no}: duplicate site_id+date ({site_val}, {date_val})"
                )
            else:
                seen_keys.add(key)

        if _cell(row, header_index, schema.OPENET_COLUMN) != "":
            openet_present += 1
        if _cell(row, header_index, schema.ETO_COLUMN) != "":
            eto_present += 1
        if _cell(row, header_index, schema.NDVI_COLUMN) != "":
            ndvi_present += 1
        if _cell(row, header_index, schema.MEASURED_COLUMN) != "":
            measured_present += 1

        if parsed_date is not None:
            if site_val not in site_rows:
                site_order.append(site_val)
                site_rows[site_val] = 0
                site_min[site_val] = parsed_date
                site_max[site_val] = parsed_date
            site_rows[site_val] += 1
            if parsed_date < site_min[site_val]:
                site_min[site_val] = parsed_date
            if parsed_date > site_max[site_val]:
                site_max[site_val] = parsed_date

    if errors:
        return ValidationResult(is_valid=False, errors=errors)

    sites = []
    for s in site_order:
        span_days = (site_max[s] - site_min[s]).days + 1
        sites.append(
            SiteSummary(
                site_id=s,
                row_count=site_rows[s],
                first_date=site_min[s].isoformat(),
                last_date=site_max[s].isoformat(),
                span_days=span_days,
            )
        )
    report = ValidationReport(
        row_count=len(data_rows),
        site_count=len(site_order),
        sites=sites,
        openet_present=openet_present,
        eto_present=eto_present,
        ndvi_present=ndvi_present,
        measured_present=measured_present,
        has_measured_labels=measured_present > 0,
    )
    return ValidationResult(is_valid=True, report=report)
```

Notes:
- **`_read_rows` is the shared parse seam** — the future source adapter reuses it to read the interchange format without re-implementing CSV handling; `schema.py` is the single source of truth for column names and bounds.
- Per-site date range tracks parsed `date` objects (not strings), so `span_days = (last - first).days + 1` gives temporal density directly.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_validator.py -q`
Expected: PASS (20 passed).

- [ ] **Step 6: Commit**

```bash
git add src/mlet/validator.py examples/et_timeseries_template.csv tests/test_validator.py
git commit -m "feat(mlet): add ET CSV validator and example template"
```

---

### Task 4: CLI entrypoint

**Files:**
- Create: `src/mlet/cli.py`
- Create: `src/mlet/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `mlet.validator.validate_csv`.
- Produces: `cli.main(argv=None) -> int` (exit code). `__main__.py` calls `sys.exit(main())` so `python -m mlet` and the `mlet` console script share one path.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
import subprocess
import sys
from pathlib import Path

import pytest

from mlet.cli import main

HEADER = "date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm\n"


def write_csv(tmp_path: Path, content: str) -> str:
    p = tmp_path / "data.csv"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_validate_valid_file_returns_0(tmp_path, capsys):
    code = main(["validate-csv", write_csv(tmp_path, HEADER + "2024-06-01,field_001,5.2,5.8,0.71,\n")])
    assert code == 0
    assert "has_measured_labels: false" in capsys.readouterr().out


def test_validate_invalid_file_returns_1(tmp_path, capsys):
    code = main(["validate-csv", write_csv(tmp_path, HEADER + "2024-06-01,field_001,abc,5.8,0.71,\n")])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_missing_argument_exits_2():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_file_not_found_returns_2(tmp_path, capsys):
    code = main(["validate-csv", str(tmp_path / "missing.csv")])
    assert code == 2
    assert "cannot read" in capsys.readouterr().err


def test_error_display_is_capped(tmp_path, capsys):
    # 25 rows with an invalid date -> 25 errors, more than MAX_DISPLAYED_ERRORS (20).
    bad_rows = "bad-date,field_001,5.2,5.8,0.71,\n" * 25
    code = main(["validate-csv", write_csv(tmp_path, HEADER + bad_rows)])
    assert code == 1
    err = capsys.readouterr().err
    assert "... and 5 more" in err


def test_module_entrypoint_matches_main(tmp_path):
    p = write_csv(tmp_path, HEADER + "2024-06-01,field_001,5.2,5.8,0.71,\n")
    proc = subprocess.run(
        [sys.executable, "-m", "mlet", "validate-csv", p],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "has_measured_labels: false" in proc.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlet.cli'`.

- [ ] **Step 3: Implement `cli.py` and `__main__.py`**

Create `src/mlet/cli.py`:

```python
"""Command-line interface for MLET."""

from __future__ import annotations

import argparse
import sys

from mlet.validator import validate_csv

# Cap how many validation errors we print, so a badly-formed file does not
# flood the terminal. The remaining count is still reported.
MAX_DISPLAYED_ERRORS = 20


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mlet")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser(
        "validate-csv", help="Validate an ET time-series CSV file."
    )
    validate.add_argument("path", help="Path to the ET time-series CSV.")
    args = parser.parse_args(argv)
    return _run_validate(args.path)


def _run_validate(path):
    try:
        result = validate_csv(path)
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    if result.is_valid:
        print(result.report.to_text())
        return 0

    shown = result.errors[:MAX_DISPLAYED_ERRORS]
    for err in shown:
        print(f"error: {err}", file=sys.stderr)
    remaining = len(result.errors) - len(shown)
    if remaining > 0:
        print(f"... and {remaining} more", file=sys.stderr)
    return 1
```

Create `src/mlet/__main__.py`:

```python
"""Enable `python -m mlet`."""

import sys

from mlet.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_cli.py -q`
Expected: PASS (6 passed). (The `python -m mlet` subprocess test relies on the editable install from Task 1.)

- [ ] **Step 5: Commit**

```bash
git add src/mlet/cli.py src/mlet/__main__.py tests/test_cli.py
git commit -m "feat(mlet): add validate-csv CLI and module entrypoint"
```

---

### Task 5: README usage note + full verification

**Files:**
- Modify: `README.md` (append a short Phase 1 usage section)

**Interfaces:**
- Consumes: the finished `mlet` package and CLI.
- Produces: nothing consumed by other tasks (final task).

- [ ] **Step 1: Add a usage section to `README.md`**

Append the following section to the end of `README.md` (do not modify existing sections):

```markdown
## Phase 1: ET time-series validation

The first MLET-owned component is a local, zero-dependency validator for daily,
site-keyed evapotranspiration CSV files. It checks structure and types and
reports contents honestly — it does not train, score, or make scientific claims.

Install and run:

```bash
python3 -m pip install -e .
mlet validate-csv examples/et_timeseries_template.csv
# or:
python3 -m mlet validate-csv examples/et_timeseries_template.csv
```

The expected CSV columns are `date` (YYYY-MM-DD), `site_id`, `openet_et_mm`
(required), and optional `eto_mm`, `ndvi`, `measured_et_mm`. A file with no
measured ET validates structurally but reports `has_measured_labels: false`.

See `docs/superpowers/specs/2026-06-28-mlet-phase1-et-csv-validator-design.md`
for the full data contract and design.
```

- [ ] **Step 2: Run the full verification suite**

Run each command and confirm the expected result:

```bash
python3 -m compileall -q src tests        # expect: no output, exit 0
python3 -m pytest -q                        # expect: 35 passed
mlet validate-csv examples/et_timeseries_template.csv   # expect: report printed, has_measured_labels: false, exit 0
```

- [ ] **Step 3: Confirm the broader repo still compiles**

Run: `git status --short`
Expected: only intended files staged/modified; `vendor/pyfao56/` untouched.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs(mlet): document Phase 1 ET CSV validation usage"
```

---

## Self-Review

**1. Spec coverage** — every spec section maps to a task:
- CSV contract / schema constants → Task 1 (`schema.py`).
- Result/report types + text rendering → Task 2 (`report.py`).
- Validation algorithm (empty, missing columns, header-only, date, numeric, duplicate, blank-OpenET completeness) → Task 3 (`validator.py`) with one test per branch.
- Report fields (row/site counts, per-site date range + temporal density, completeness/availability, `has_measured_labels`) → Task 2 rendering + Task 3 computation, asserted in `test_report_stats_and_date_range` and `test_density_reported_for_gappy_site`.
- CLI subcommand, both invocation paths, exit codes 0/1/2 → Task 4 (`cli.py`, `__main__.py`).
- Example template + "shipped template validates" → Task 3.
- Packaging (PEP 621, src layout, console script, pytest config, zero deps, `>=3.9`) → Task 1 `pyproject.toml`.
- Verification commands (`compileall`, `pytest`, CLI run) → Task 5.

**2. Placeholder scan** — no TBD/TODO; every code step shows complete file content; every test step shows real assertions.

**3. Type consistency** — names match across tasks: `ValidationResult(is_valid, errors, report)`, `ValidationReport(row_count, site_count, sites, openet_present, eto_present, ndvi_present, measured_present, has_measured_labels)`, `SiteSummary(site_id, row_count, first_date, last_date, span_days)`, `validate_csv(path) -> ValidationResult`, `cli.main(argv) -> int`. Schema constant names (`REQUIRED_COLUMNS`, `NUMERIC_COLUMNS`, `NONNEGATIVE_COLUMNS`, `NDVI_MIN`, `NDVI_MAX`, `DATE_COLUMN`, …) are used identically in `validator.py`.

Total expected test count across the suite: 6 (package) + 3 (report) + 20 (validator) + 6 (cli) = 35.

### Post-review additions (from /plan-eng-review)
- `encoding="utf-8-sig"` so Excel BOM does not corrupt the header (Task 3) — test `test_utf8_bom_header_is_handled`.
- Reject non-finite numerics via `math.isfinite` (Task 3) — tests `test_non_finite_numeric_fails`, `test_inf_numeric_fails`.
- Cover the CLI error-display cap branch (Task 4) — test `test_error_display_is_capped`.
- Ragged rows reviewed and intentionally left lenient (Global Constraints).

---

## NOT in scope (considered and deferred)

- **Streaming / chunked CSV reading** — Phase 1 files are template-scale; `list(csv.reader(f))` is fine. Revisit when field-season-scale data arrives.
- **Physical-validity checks** (ET ≥ 0, NDVI ∈ [-1, 1]) — **now in scope** as hard errors (catch negative nodata sentinels by physics).
- **Agronomic range checks** (typical NDVI ranges, future-dated rows) and an **upper ET corruption ceiling** (e.g. `ET ≤ 50` to catch positive sentinels like `9999`) — deferred; better added later as non-fatal warnings.
- **Explicit `--na-value`** declaration of source fill values — deferred until a real source needs sentinel-as-missing; the adapter normalizes fills to blank meanwhile.
- **Provenance / latency** (an `as_of` / `source` field, à la pyfao56 `MorP`) — reserved as the named first schema extension; introduced when assimilation work begins.
- **Canonical loader / record types** — Phase 1 ships only the internal `_read_rows` parse seam; a typed loader is built when the adapter/modeling phase has a real consumer.
- **Batch / multi-file CLI** — single-file only; batch is a thin CLI loop over the reusable `validate_csv()` later.
- **Ragged-row rejection** — reviewed; intentionally lenient (missing trailing cells read as blank).
- **Alternate delimiters** (`;` for EU Excel locales), alternate date formats, `--json` output — YAGNI for Phase 1; the contract is comma-delimited ISO CSV with a structured report object ready for a later `--json`.
- **pandas / numpy** — deferred to modeling phases per the approved spec.

## What already exists

- **`vendor/pyfao56`** — FAO-56 water balance math. Unrelated to CSV validation; correctly **not reused** and left untouched.
- **`README.md`** — broader project direction. Task 5 appends a Phase 1 usage note; existing sections untouched.
- **No prior MLET package / CSV schema / validator** — confirmed greenfield. Nothing is rebuilt.

## Failure modes

| Codepath | Failure | Test | Error handling | User sees |
|----------|---------|------|----------------|-----------|
| `open()` | file missing/locked | ✓ | ✓ OSError→exit 2 | clear "cannot read" |
| header parse | Excel BOM | ✓ | ✓ utf-8-sig | **correct** (was critical gap) |
| numeric parse | `nan`/`inf` | ✓ | ✓ isfinite | row-context error |
| numeric parse | non-numeric string | ✓ | ✓ | row-context error |
| numeric value | negative ET / `-9999` sentinel | ✓ | ✓ `>= 0` check | row-context error |
| numeric value | NDVI outside `[-1,1]` / sentinel | ✓ | ✓ bounds check | row-context error |
| numeric value | positive ET sentinel (`9999`) | ✓ (documents gap) | ✗ deferred | **passes** — known Phase-1 limitation |
| row width | truncated row | — | lenient (by decision) | counts as incomplete |

No remaining critical gaps. The one documented residual is the positive-ET sentinel (`9999`), intentionally deferred to a later ET corruption-ceiling / `--na-value`; a test pins the current behavior so it surfaces loudly when that lands.

## Worktree parallelization strategy

| Step | Modules touched | Depends on |
|------|-----------------|------------|
| Task 1 scaffold + schema | `pyproject.toml`, `src/mlet/` | — |
| Task 2 report | `src/mlet/report.py` | Task 1 |
| Task 3 validator + template | `src/mlet/validator.py`, `examples/` | Tasks 1, 2 |
| Task 4 cli | `src/mlet/cli.py`, `src/mlet/__main__.py` | Task 3 |
| Task 5 readme + verify | `README.md` | Task 4 |

**Sequential implementation, no meaningful parallelization opportunity** — every task shares the `src/mlet/` module and builds on the prior task's types (report ← validator ← cli). Worktree isolation would add overhead with no wall-clock gain.

## Implementation Tasks (synthesized from review)

All three review findings are folded directly into the plan tasks above — no separate follow-up work:

- [ ] **T1 (P1, human ~20m / CC ~5m)** — validator — utf-8-sig encoding + BOM test. Surfaced by: Architecture review (BOM blind spot). Files: `src/mlet/validator.py`, `tests/test_validator.py`. Verify: `pytest tests/test_validator.py::test_utf8_bom_header_is_handled`.
- [ ] **T2 (P2, human ~15m / CC ~5m)** — validator — `math.isfinite` guard + nan/inf tests. Surfaced by: Code quality (float accepts nan/inf). Files: `src/mlet/validator.py`, `tests/test_validator.py`. Verify: `pytest tests/test_validator.py -k non_finite or inf`.
- [ ] **T3 (P2, human ~10m / CC ~3m)** — cli — cover error-display cap branch. Surfaced by: Test review (untested `if remaining > 0`). Files: `tests/test_cli.py`. Verify: `pytest tests/test_cli.py::test_error_display_is_capped`.

## Post-grilling refinements

A `/grill-me` pass walked the design tree and folded nine decisions into the plan above. All are reflected in the task code/tests; no separate follow-up tasks.

1. **Interchange format + adapter** — the contract is explicitly an interchange/validation format between raw source exports and pyfao56 (`eto_mm` ⇄ `ETref`); an adapter layer is the planned next piece.
2. **Validation-only, clean parse seam** — `_read_rows` is the shared seam; `schema.py` is the single source of truth. No loader/record types yet.
3. **Provenance/latency deferred but reserved** — named first schema extension (à la pyfao56 `MorP` / an `as_of` field).
4. **`label_ready` → `has_measured_labels`** — presence flag, honest about what Phase 1 can assert; coverage-gated `label_ready` returns later.
5. **Per-site temporal density** — span vs rows, non-fatal, surfaces gappy series.
6+7. **Sentinels caught by physics** — `ET ≥ 0`, `NDVI ∈ [-1,1]` as hard errors. Reverses the earlier blanket "defer domain ranges" for the impossible-value subset only; agronomic ranges + positive-ET ceiling + `--na-value` stay deferred (positive-ET sentinel gap documented + pinned by a test).
8. **CLI stays single-file** — batch deferred.
9. **Text output now** — `--json` deferred; the report dataclass makes it a trivial later add.

Net effect on tests: **29 → 35** (package 5→6, validator 15→20; renames in cli/report).

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | not run |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | not run |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 4 issues (1 P1, 2 P2, 1 P3-noted); 1 critical gap closed |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | n/a (no UI) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | not run |

- **Scope:** accepted as-is (no reduction needed; new-package multi-file layout is appropriate).
- **Decisions:** BOM → utf-8-sig (accepted); nan/inf → reject (accepted); ragged rows → keep lenient (accepted).
- **UNRESOLVED:** none.
- **Critical gaps:** 0 remaining (BOM gap closed).
- **Outside voice:** not run (small, self-authored stdlib plan; offer stands if you want a Codex second opinion).
- **VERDICT:** ENG CLEARED — ready to implement.
