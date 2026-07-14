"""Parse one public flux-tower daily file for Phase 2 labels and covariates."""
from __future__ import annotations

import csv
from dataclasses import dataclass


@dataclass(frozen=True)
class FluxDaily:
    et_corr: float | None
    et_gap: bool
    gridmet_eto: float | None
    t_avg: float | None
    vpd: float | None
    ws: float | None
    ppt: float | None


def _number(row: dict[str, str], key: str) -> float | None:
    value = (row.get(key) or "").strip()
    return float(value) if value else None


def load_flux_daily(path: str) -> dict[str, FluxDaily]:
    result: dict[str, FluxDaily] = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            date = (row.get("date") or "").strip()
            if not date:
                continue
            result[date] = FluxDaily(
                et_corr=_number(row, "ET_corr"),
                et_gap=(row.get("ET_gap") or "").strip().lower() == "true",
                gridmet_eto=_number(row, "gridMET_ETo"),
                t_avg=_number(row, "t_avg"),
                vpd=_number(row, "vpd"),
                ws=_number(row, "ws"),
                ppt=_number(row, "ppt"),
            )
    return result
