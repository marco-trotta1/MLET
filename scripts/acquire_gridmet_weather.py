"""Extract daily gridMET weather at the benchmark station locations."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from ssl import create_default_context
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import certifi
import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mlet.sources.gridmet_weather import decode_gridmet_value
from mlet.sources.stations import load_station_metadata

BASE_URL = "https://thredds.northwestknowledge.net/thredds/ncss/grid/MET"
VARIABLES = {
    "vs": "wind_speed",
    "tmmn": "air_temperature",
    "tmmx": "air_temperature",
    "vpd": "mean_vapor_pressure_deficit",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_subset(
    station_id: str,
    year: int,
    variable: str,
    latitude: float,
    longitude: float,
    start: str,
    end: str,
    cache_dir: Path,
) -> tuple[pd.Series, float, float, str]:
    """Fetch one annual point series and return values and source coordinates."""
    filename = f"{station_id}_{year}_{variable}.nc"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / filename
    url = f"{BASE_URL}/{variable}/{variable}_{year}.nc"
    query = urlencode(
        {
            "var": VARIABLES[variable],
            "latitude": latitude,
            "longitude": longitude,
            "time_start": start,
            "time_end": end,
            "accept": "netcdf",
            "cacheBust": f"{station_id}_{year}_{variable}",
        }
    )
    context = create_default_context(cafile=certifi.where())
    last_error: Exception | None = None
    for attempt in range(4):
        if not path.exists():
            try:
                with urlopen(f"{url}?{query}", context=context, timeout=180) as response:
                    content = response.read()
                if not content.startswith((b"\x89HDF\r\n\x1a\n", b"CDF\x01", b"CDF\x02")):
                    raise ValueError(f"gridMET returned a non-NetCDF response for {filename}")
                temporary = path.with_suffix(".nc.tmp")
                temporary.write_bytes(content)
                temporary.replace(path)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(1.5 * (attempt + 1))
                continue
        try:
            with xr.open_dataset(path, mask_and_scale=False) as dataset:
                if "time" not in dataset or VARIABLES[variable] not in dataset:
                    raise ValueError(f"gridMET subset has an invalid schema: {filename}")
                raw = dataset[VARIABLES[variable]].to_numpy().astype(float)
                dates = pd.to_datetime(dataset["time"].to_numpy()).normalize()
                latitude_out = float(dataset["latitude"].to_numpy().reshape(-1)[0])
                longitude_out = float(dataset["longitude"].to_numpy().reshape(-1)[0])
                title = str(dataset.attrs.get("title", ""))
                description = dataset["station_description"].to_numpy().reshape(-1)[0]
                description = description.decode() if isinstance(description, bytes) else str(description)
            match = re.search(r"lat/lon=([-+0-9.]+),([-+0-9.]+)", description)
            expected_title = f"/{variable}_{year}.nc"
            valid_response = (
                expected_title in title
                and match is not None
                and abs(float(match.group(1)) - latitude) <= 0.000005
                and abs(float(match.group(2)) - longitude) <= 0.000005
                and len(dates) > 0
                and (dates >= pd.Timestamp(start)).all()
                and (dates <= pd.Timestamp(end)).all()
            )
            if valid_response:
                break
            last_error = ValueError(f"gridMET response identity mismatch for {filename}")
            path.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError) as exc:
            last_error = exc
            path.unlink(missing_ok=True)
    else:
        raise RuntimeError(f"gridMET request failed for {filename}: {last_error}")
    valid = np.isfinite(raw) & (raw != 32767) & (raw >= 0)
    decoded = np.full(raw.shape, np.nan, dtype=float)
    decoded[valid] = [decode_gridmet_value(variable, value) for value in raw[valid]]
    values = pd.Series(decoded, index=dates, name=variable)
    if values.index.has_duplicates:
        raise ValueError(f"gridMET returned duplicate dates for {filename}")
    return values, latitude_out, longitude_out, sha256(path)


def build_weather(
    joined_path: Path,
    metadata_path: Path,
    cache_dir: Path,
    output_path: Path,
) -> dict:
    joined = pd.read_csv(joined_path, parse_dates=["date"])
    metadata = load_station_metadata(str(metadata_path))
    if set(joined.site_id.unique()) != set(metadata):
        raise ValueError("joined station IDs do not match the station metadata")
    joined["year"] = joined.date.dt.year
    station_years = joined.groupby(["site_id", "year"], sort=True)
    tasks = []
    for (station_id, year), rows in station_years:
        station = metadata[str(station_id)]
        dates = rows.date.dt.strftime("%Y-%m-%d")
        tasks.append(
            (
                str(station_id),
                int(year),
                station.latitude,
                station.longitude,
                dates.min(),
                dates.max(),
            )
        )
    cache_dir.mkdir(parents=True, exist_ok=True)
    observations: list[dict] = []
    hashes: dict[str, str] = {}
    for number, task in enumerate(tasks, start=1):
        station_id, year, data, files = _fetch_station_year(task, cache_dir)
        observations.extend(data)
        hashes.update(files)
        if number % 25 == 0 or number == len(tasks):
            print(f"Fetched {number}/{len(tasks)} station-years", flush=True)

    weather = pd.DataFrame(observations)
    if weather.duplicated(["site_id", "date"]).any():
        raise ValueError("gridMET output contains duplicate station dates")
    result = joined.drop(columns="year").merge(
        weather, on=["site_id", "date"], how="left", validate="one_to_one"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False, float_format="%.6f")
    receipt = {
        "source": "gridMET daily point subsets",
        "catalog": "https://thredds.northwestknowledge.net/thredds/catalog/MET/",
        "years": [int(result.date.dt.year.min()), int(result.date.dt.year.max())],
        "joined_rows": int(len(joined)),
        "stations": int(joined.site_id.nunique()),
        "station_years": int(len(tasks)),
        "variables": {
            "vs": {"field": "wind_speed", "unit": "m/s", "decode": "0.1 * packed"},
            "tmmn": {"field": "air_temperature", "unit": "K", "decode": "0.1 * packed + 210"},
            "tmmx": {"field": "air_temperature", "unit": "K", "decode": "0.1 * packed + 220"},
            "vpd": {"field": "mean_vapor_pressure_deficit", "unit": "kPa", "decode": "0.01 * packed"},
        },
        "derived_features": {
            "t_min_c": "tmmn_K - 273.15",
            "t_max_c": "tmmx_K - 273.15",
            "t_avg_c": "(tmmn_K + tmmx_K) / 2 - 273.15",
            "vpd_kpa": "native gridMET vpd",
            "wind_m_s": "native gridMET vs at 10 m",
        },
        "complete_weather_rows": int(result[["t_avg_c", "vpd_kpa", "wind_m_s"]].notna().all(axis=1).sum()),
        "source_files": hashes,
        "output_sha256": sha256(output_path),
    }
    receipt_path = output_path.with_suffix(".receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def _fetch_station_year(task: tuple, cache_dir: Path) -> tuple[str, int, list[dict], dict[str, str]]:
    station_id, year, latitude, longitude, start, end = task
    frames = {}
    file_hashes = {}
    grid_latitude = None
    grid_longitude = None
    for variable in VARIABLES:
        values, grid_latitude, grid_longitude, file_hash = request_subset(
            station_id,
            year,
            variable,
            latitude,
            longitude,
            start,
            end,
            cache_dir,
        )
        frames[variable] = values
        file_hashes[f"{station_id}_{year}_{variable}.nc"] = file_hash
    daily = pd.concat(frames.values(), axis=1)
    daily["t_min_c"] = daily.tmmn - 273.15
    daily["t_max_c"] = daily.tmmx - 273.15
    daily["t_avg_c"] = (daily.tmmn + daily.tmmx) / 2.0 - 273.15
    daily = daily.rename(columns={"vpd": "vpd_kpa", "vs": "wind_m_s"})
    daily["site_id"] = station_id
    daily["date"] = daily.index
    daily["station_latitude"] = latitude
    daily["station_longitude"] = longitude
    selected = daily.loc[
        (daily.index >= pd.Timestamp(start)) & (daily.index <= pd.Timestamp(end)),
        [
            "site_id", "date", "t_min_c", "t_max_c", "t_avg_c", "vpd_kpa",
            "wind_m_s", "station_latitude", "station_longitude",
        ],
    ]
    return station_id, year, selected.to_dict("records"), file_hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--joined", type=Path, default=ROOT / "data/interim/all_stations.csv")
    parser.add_argument(
        "--metadata",
        type=Path,
        default=ROOT / "data/raw/openet_phase2/OpenET_PhaseII_model_ET_dataset/Station_metadata.xlsx",
    )
    parser.add_argument("--cache", type=Path, default=ROOT / "data/raw/gridmet_weather")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/results/ml_tier1_selective/gridmet_weather.csv"
    )
    args = parser.parse_args()
    receipt = build_weather(args.joined, args.metadata, args.cache, args.output)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
