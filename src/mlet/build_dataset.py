"""Join public Phase 2 inputs into validator-gated Phase 1 contract CSVs."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from mlet import schema
from mlet.sources.flux import load_flux_daily
from mlet.sources.openet import load_openet_ensemble
from mlet.sources.stations import load_station_metadata
from mlet.validator import validate_csv


@dataclass(frozen=True)
class BuildStats:
    stations: int
    rows_written: int
    labeled_rows: int
    dropped_gap: int
    dropped_missing_eto: int


def _format(value: float | None) -> str:
    return "" if value is None else str(value)


def _write_contract(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(schema.ALL_COLUMNS)
        writer.writerows(rows)


def build_dataset(
    openet_dat: str, flux_dir: str, metadata_xlsx: str, out_dir: str
) -> BuildStats:
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    openet = load_openet_ensemble(openet_dat)
    metadata = load_station_metadata(metadata_xlsx)
    station_ids = sorted({station_id for station_id, _ in openet})
    all_rows: list[list[str]] = []
    land_cover: dict[str, str] = {}
    weather: dict[str, dict[str, dict[str, float | None]]] = {}
    labeled_rows = dropped_gap = dropped_missing_eto = 0
    written_stations = 0

    for station_id in station_ids:
        flux_path = Path(flux_dir) / f"{station_id}_daily_data.csv"
        if not flux_path.exists():
            continue
        flux = load_flux_daily(str(flux_path))
        rows: list[list[str]] = []
        station_weather: dict[str, dict[str, float | None]] = {}
        dates = sorted(date for candidate, date in openet if candidate == station_id)
        for date in dates:
            flux_day = flux.get(date)
            if flux_day is None:
                continue
            if flux_day.gridmet_eto is None:
                dropped_missing_eto += 1
                continue
            label: float | None = flux_day.et_corr
            if flux_day.et_gap or label is None:
                label = None
                dropped_gap += int(flux_day.et_gap)
            else:
                labeled_rows += 1
            rows.append([
                date,
                station_id,
                _format(openet[(station_id, date)]),
                _format(flux_day.gridmet_eto),
                "",
                _format(label),
            ])
            station_weather[date] = {
                "t_avg": flux_day.t_avg,
                "vpd": flux_day.vpd,
                "ws": flux_day.ws,
                "ppt": flux_day.ppt,
            }
        if not rows:
            continue
        station_path = destination / f"{station_id}.csv"
        _write_contract(station_path, rows)
        result = validate_csv(station_path)
        if not result.is_valid:
            raise RuntimeError(f"built CSV failed Phase 1 validation for {station_id}: {result.errors}")
        written_stations += 1
        all_rows.extend(rows)
        weather[station_id] = station_weather
        if station_id in metadata:
            land_cover[station_id] = metadata[station_id].land_cover

    _write_contract(destination / "all_stations.csv", all_rows)
    with (destination / "_landcover.json").open("w", encoding="utf-8") as handle:
        json.dump(land_cover, handle, indent=2, sort_keys=True)
    with (destination / "_weather.json").open("w", encoding="utf-8") as handle:
        json.dump(weather, handle, indent=2, sort_keys=True)
    return BuildStats(
        stations=written_stations,
        rows_written=len(all_rows),
        labeled_rows=labeled_rows,
        dropped_gap=dropped_gap,
        dropped_missing_eto=dropped_missing_eto,
    )
