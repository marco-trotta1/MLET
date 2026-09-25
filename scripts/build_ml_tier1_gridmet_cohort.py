"""Build the fixed all-station gridMET cohort for Tier 1 evaluation."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mlet.sources.stations import load_station_metadata

OUT = ROOT / "docs/results/ml_tier1_gridmet"
PROTOCOL = ROOT / "docs/evaluation/ML_TIER1_GRIDMET_PROTOCOL.md"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def saturation_vapor_pressure(temperature_c: pd.Series) -> pd.Series:
    return 0.6108 * np.exp(17.27 * temperature_c / (temperature_c + 237.3))


def gridmet_screen(frame: pd.DataFrame) -> pd.DataFrame:
    """Return per-rule validity flags for gridMET values."""
    saturation = saturation_vapor_pressure(frame.t_max_c)
    return pd.DataFrame(
        {
            "wind_valid": frame.wind_m_s.between(0, 75),
            "temperature_valid": frame.t_min_c.between(-50, 60)
            & frame.t_max_c.between(-50, 60)
            & (frame.t_min_c <= frame.t_max_c),
            "vpd_valid": frame.vpd_kpa.ge(0) & (frame.vpd_kpa <= saturation),
        },
        index=frame.index,
    ).fillna(False)


def join_gridmet_weather(joined: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    weather_columns = [
        "site_id",
        "date",
        "t_min_c",
        "t_max_c",
        "t_avg_c",
        "vpd_kpa",
        "wind_m_s",
        "station_latitude",
        "station_longitude",
    ]
    return joined.merge(
        weather[weather_columns],
        on=["site_id", "date"],
        validate="one_to_one",
    )


def sensor_fault_flags(frame: pd.DataFrame) -> pd.DataFrame:
    """Flag observed station weather values that violate the fixed screen."""
    vapor_pressure = pd.to_numeric(frame.vp_kpa, errors="coerce")
    vpd = pd.to_numeric(frame.vpd_kpa_sensor, errors="coerce")
    saturation = pd.to_numeric(frame.es_kpa, errors="coerce")
    wind = pd.to_numeric(frame.ws_sensor, errors="coerce")
    temperature = pd.to_numeric(frame.t_avg_sensor, errors="coerce")
    vpd_has_saturation = vpd.notna() & saturation.notna()
    return pd.DataFrame(
        {
            "sensor_vapor_pressure_invalid": vapor_pressure.notna()
            & vapor_pressure.lt(0),
            "sensor_vpd_invalid": vpd.notna()
            & (vpd.lt(0) | (vpd_has_saturation & vpd.gt(saturation))),
            "sensor_wind_invalid": wind.notna() & ~wind.between(0, 75),
            "sensor_temperature_invalid": temperature.notna()
            & ~temperature.between(-50, 60),
        },
        index=frame.index,
    ).fillna(False)


def proximity_groups(metadata: dict, stations: list[str], threshold_km: float) -> dict[str, str]:
    parent = {station: station for station in stations}

    def root(station: str) -> str:
        while parent[station] != station:
            station = parent[station]
        return station

    for index, first in enumerate(stations):
        for second in stations[index + 1 :]:
            a, b = metadata[first], metadata[second]
            lat1, lat2 = np.radians([a.latitude, b.latitude])
            dlat = lat2 - lat1
            dlon = np.radians(b.longitude - a.longitude)
            h = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
            distance = 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
            if distance <= threshold_km:
                parent[root(second)] = root(first)
    return {station: root(station) for station in stations}


def source_weather(root: Path, station_ids: list[str]) -> tuple[pd.DataFrame, dict[str, str]]:
    flux = root / "data/raw/flux_et/flux_ET_dataset/daily_data_files"
    frames = []
    hashes = {}
    columns = ["date", "t_avg", "vpd", "ws", "vp", "es"]
    for station in station_ids:
        path = flux / f"{station}_daily_data.csv"
        values = pd.read_csv(path, parse_dates=["date"], usecols=lambda name: name in columns)
        values = values.reindex(columns=columns)
        values["site_id"] = station
        values = values.rename(
            columns={
                "t_avg": "t_avg_sensor",
                "vpd": "vpd_kpa_sensor",
                "ws": "ws_sensor",
                "vp": "vp_kpa",
                "es": "es_kpa",
            }
        )
        frames.append(values)
        hashes[path.name] = sha256(path)
    return pd.concat(frames, ignore_index=True), hashes


def build_cohort() -> dict:
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite results in {OUT}")
    OUT.mkdir(parents=True)
    joined_path = ROOT / "data/interim/all_stations.csv"
    metadata_path = ROOT / "data/raw/openet_phase2/OpenET_PhaseII_model_ET_dataset/Station_metadata.xlsx"
    weather_path = ROOT / "docs/results/ml_tier1_selective/gridmet_weather.csv"
    weather_receipt_path = weather_path.with_suffix(".receipt.json")
    joined = pd.read_csv(joined_path, parse_dates=["date"])
    weather = pd.read_csv(weather_path, parse_dates=["date"])
    metadata = load_station_metadata(str(metadata_path))
    source, source_hashes = source_weather(ROOT, sorted(joined.site_id.unique()))
    frame = join_gridmet_weather(joined, weather)
    frame = frame.merge(source, on=["site_id", "date"], how="left", validate="one_to_one")
    grid_flags = gridmet_screen(frame)
    sensor_flags = sensor_fault_flags(frame)
    required = frame[
        [
            "measured_et_mm", "openet_et_mm", "eto_mm", "t_min_c", "t_max_c",
            "t_avg_c", "vpd_kpa", "wind_m_s",
        ]
    ].notna().all(axis=1)
    frame["gridmet_valid"] = grid_flags.all(axis=1)
    frame["sensor_fault"] = sensor_flags.any(axis=1)
    frame["eligible"] = required & frame.gridmet_valid & ~frame.sensor_fault
    frame["failed_gridmet_rules"] = grid_flags.apply(
        lambda row: ";".join(row.index[~row.to_numpy()]), axis=1
    )
    frame["failed_sensor_rules"] = sensor_flags.apply(
        lambda row: ";".join(row.index[row.to_numpy()]), axis=1
    )

    selected = frame.loc[frame.eligible].copy()
    selected = selected.rename(
        columns={
            "site_id": "station",
            "measured_et_mm": "y",
            "openet_et_mm": "openet",
            "eto_mm": "eto",
        }
    )
    selected["year"] = selected.date.dt.year
    selected["doy"] = selected.date.dt.dayofyear
    selected["doy_sin"] = np.sin(2 * np.pi * selected.doy / 365)
    selected["doy_cos"] = np.cos(2 * np.pi * selected.doy / 365)
    selected["t_avg"] = selected.t_avg_c
    selected["vpd"] = selected.vpd_kpa
    selected["ws"] = selected.wind_m_s
    selected["landcover"] = selected.station.map(
        {key: value.land_cover for key, value in metadata.items()}
    )
    groups = proximity_groups(metadata, sorted(selected.station.unique()), 10.0)
    selected["group"] = selected.station.map(groups)
    selected = selected.sort_values(["station", "date"]).reset_index(drop=True)
    selected.insert(0, "row_id", np.arange(len(selected)))
    model_columns = ["openet", "eto", "doy_sin", "doy_cos", "t_avg", "vpd", "ws", "y"]
    if not np.isfinite(selected[model_columns].to_numpy()).all():
        raise ValueError("selected cohort has a nonfinite model value")
    if selected.duplicated(["station", "date"]).any():
        raise ValueError("selected cohort has duplicate station dates")
    selected.to_csv(OUT / "cohort.csv", index=False, float_format="%.8f")
    frame.to_csv(OUT / "physical_audit.csv", index=False, float_format="%.8f")
    receipt = {
        "protocol_sha256": sha256(PROTOCOL),
        "builder_sha256": sha256(Path(__file__)),
        "joined_sha256": sha256(joined_path),
        "metadata_sha256": sha256(metadata_path),
        "gridmet_table_sha256": sha256(weather_path),
        "gridmet_receipt_sha256": sha256(weather_receipt_path),
        "source_weather_sha256": source_hashes,
        "labeled_rows": int(len(joined)),
        "labeled_stations": int(joined.site_id.nunique()),
        "complete_gridmet_rows": int(required.sum()),
        "missing_required_values": {
            name: int(frame[name].isna().sum())
            for name in [
                "measured_et_mm", "openet_et_mm", "eto_mm", "t_min_c", "t_max_c",
                "t_avg_c", "vpd_kpa", "wind_m_s",
            ]
        },
        "gridmet_rule_failures": {name: int((~grid_flags[name]).sum()) for name in grid_flags},
        "observed_sensor_fault_counts": {
            name: int(sensor_flags[name].sum()) for name in sensor_flags
        },
        "rows_with_observed_sensor_faults": int(sensor_flags.any(axis=1).sum()),
        "eligible_rows": int(len(selected)),
        "eligible_stations": int(selected.station.nunique()),
        "proximity_groups": int(selected.group.nunique()),
        "year_rows": {
            str(year): int(count)
            for year, count in selected.year.value_counts().sort_index().items()
        },
    }
    (OUT / "cohort_receipt.json").write_text(json.dumps(receipt, indent=2) + chr(10))
    print(json.dumps(receipt, indent=2))
    return receipt


if __name__ == "__main__":
    build_cohort()
