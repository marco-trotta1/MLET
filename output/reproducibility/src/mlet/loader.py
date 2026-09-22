"""Typed per-site loader over the Phase 1 ET CSV contract."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime

from mlet import schema


@dataclass(frozen=True)
class DailyRecord:
    date: date
    openet_et_mm: float | None
    eto_mm: float | None
    measured_et_mm: float | None


@dataclass(frozen=True)
class SiteSeries:
    site_id: str
    records: list[DailyRecord]

    def labeled(self) -> list[DailyRecord]:
        return [record for record in self.records if record.measured_et_mm is not None]

    @property
    def label_ready(self) -> bool:
        return len(self.labeled()) >= schema.MIN_LABELED_DAYS


def _number(value: str | None) -> float | None:
    return float(value) if value and value.strip() else None


def load_site_series(path: str) -> SiteSeries:
    records: list[DailyRecord] = []
    site_ids: set[str] = set()
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            site_id = (row.get(schema.SITE_COLUMN) or "").strip()
            if not site_id:
                continue
            site_ids.add(site_id)
            records.append(DailyRecord(
                date=datetime.strptime(row[schema.DATE_COLUMN], schema.DATE_FORMAT).date(),
                openet_et_mm=_number(row.get(schema.OPENET_COLUMN)),
                eto_mm=_number(row.get(schema.ETO_COLUMN)),
                measured_et_mm=_number(row.get(schema.MEASURED_COLUMN)),
            ))
    if len(site_ids) > 1:
        raise ValueError(f"expected one site per CSV, found: {sorted(site_ids)}")
    records.sort(key=lambda record: record.date)
    return SiteSeries(site_id=next(iter(site_ids), ""), records=records)
