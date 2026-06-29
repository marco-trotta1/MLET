"""Validate daily, site-keyed ET time-series CSV files."""

from __future__ import annotations

import csv
import math
import os
from datetime import datetime

from mlet import schema
from mlet.report import SiteSummary, ValidationReport, ValidationResult


def _cell(row: list[str], header_index: dict[str, int], name: str) -> str:
    """Return the stripped column value, treating missing optional cells as blank."""
    if name not in header_index:
        return ""
    index = header_index[name]
    return row[index].strip() if index < len(row) else ""


def _read_rows(
    path: str | os.PathLike[str],
) -> tuple[list[str] | None, dict[str, int] | None, list[list[str]] | None]:
    """Read CSV rows through the shared future adapter seam.

    `utf-8-sig` strips Excel's UTF-8 BOM from the first header name. OSError is
    allowed to propagate so the CLI can distinguish I/O from invalid content.
    """
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        rows = list(csv.reader(csv_file))
    if not rows:
        return None, None, None

    header = [cell.strip() for cell in rows[0]]
    header_index = {name: index for index, name in enumerate(header)}
    return header, header_index, rows[1:]


def validate_csv(path: str | os.PathLike[str]) -> ValidationResult:
    """Validate an ET time-series CSV and return a structured result."""
    header, header_index, data_rows = _read_rows(path)

    if header is None or header_index is None or data_rows is None:
        return ValidationResult(is_valid=False, errors=["file is empty"])

    missing = [column for column in schema.REQUIRED_COLUMNS if column not in header]
    if missing:
        return ValidationResult(
            is_valid=False,
            errors=[f"missing required column(s): {', '.join(missing)}"],
        )

    if not data_rows:
        return ValidationResult(is_valid=False, errors=["no usable time-series rows"])

    errors: list[str] = []
    seen_keys: set[tuple[str, str]] = set()

    site_order: list[str] = []
    site_rows: dict[str, int] = {}
    site_min = {}
    site_max = {}

    openet_present = 0
    eto_present = 0
    ndvi_present = 0
    measured_present = 0

    for offset, row in enumerate(data_rows):
        line_no = offset + 2

        date_value = _cell(row, header_index, schema.DATE_COLUMN)
        site_value = _cell(row, header_index, schema.SITE_COLUMN)

        parsed_date = None
        try:
            parsed_date = datetime.strptime(date_value, schema.DATE_FORMAT).date()
        except ValueError:
            errors.append(
                f"row {line_no}: invalid date {date_value!r} (expected YYYY-MM-DD)"
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
            if name in schema.NONNEGATIVE_COLUMNS and value < 0:
                errors.append(f"row {line_no}: {name} must be >= 0, got {value}")
            elif name == schema.NDVI_COLUMN and not (
                schema.NDVI_MIN <= value <= schema.NDVI_MAX
            ):
                errors.append(f"row {line_no}: ndvi must be in [-1, 1], got {value}")

        if parsed_date is not None:
            key = (site_value, date_value)
            if key in seen_keys:
                errors.append(
                    f"row {line_no}: duplicate site_id+date ({site_value}, "
                    f"{date_value})"
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
            if site_value not in site_rows:
                site_order.append(site_value)
                site_rows[site_value] = 0
                site_min[site_value] = parsed_date
                site_max[site_value] = parsed_date
            site_rows[site_value] += 1
            if parsed_date < site_min[site_value]:
                site_min[site_value] = parsed_date
            if parsed_date > site_max[site_value]:
                site_max[site_value] = parsed_date

    if errors:
        return ValidationResult(is_valid=False, errors=errors)

    sites = []
    for site_id in site_order:
        span_days = (site_max[site_id] - site_min[site_id]).days + 1
        sites.append(
            SiteSummary(
                site_id=site_id,
                row_count=site_rows[site_id],
                first_date=site_min[site_id].isoformat(),
                last_date=site_max[site_id].isoformat(),
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
