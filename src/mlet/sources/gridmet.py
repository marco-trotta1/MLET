"""Nearest-cell reference-ET extraction from gridMET NetCDF."""
from __future__ import annotations

import numpy as np
import xarray as xr

_VARIABLE = "potential_evapotranspiration"


def extract_eto(
    nc_paths: list[str], lat: float, lon: float, dates: list[str]
) -> dict[str, float]:
    wanted = np.array(dates, dtype="datetime64[ns]")
    result: dict[str, float] = {}
    for path in nc_paths:
        with xr.open_dataset(path) as dataset:
            series = dataset[_VARIABLE].sel(lat=lat, lon=lon, method="nearest")
            available = np.intersect1d(wanted, series["day"].values)
            if not available.size:
                continue
            values = series.sel(day=available).values
            for day, value in zip(available, values, strict=True):
                result[np.datetime_as_string(day, unit="D")] = float(value)
    return result
