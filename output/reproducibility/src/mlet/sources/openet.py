"""Parse the OpenET Phase II daily ensemble table."""
from __future__ import annotations

import csv


def load_openet_ensemble(path: str) -> dict[tuple[str, str], float]:
    with open(path, encoding="utf-8-sig") as handle:
        lines = handle.read().splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.startswith("Site ID"))
    except StopIteration as exc:
        raise ValueError("OpenET daily table has no 'Site ID' header") from exc
    reader = csv.DictReader(lines[start:], delimiter="\t")
    if reader.fieldnames is None or "Ensemble" not in reader.fieldnames or "DATE" not in reader.fieldnames:
        raise ValueError("OpenET daily table is missing Ensemble or DATE")
    result: dict[tuple[str, str], float] = {}
    for row in reader:
        station_id = (row.get("Site ID") or "").strip()
        date = (row.get("DATE") or "").strip()
        ensemble = (row.get("Ensemble") or "").strip()
        if station_id and date and ensemble:
            result[(station_id, date)] = float(ensemble)
    return result
