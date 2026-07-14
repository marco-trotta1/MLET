import numpy as np
import xarray as xr

from mlet.sources.gridmet import extract_eto


def _tiny_nc(path: str) -> None:
    days = np.array(["2020-06-01", "2020-06-02"], dtype="datetime64[ns]")
    lat = np.array([36.5, 36.8, 37.0])
    lon = np.array([-98.0, -97.8, -97.5])
    data = np.arange(18, dtype=float).reshape(2, 3, 3)
    dataset = xr.Dataset(
        {"potential_evapotranspiration": (("day", "lat", "lon"), data)},
        coords={"day": days, "lat": lat, "lon": lon},
    )
    dataset.to_netcdf(path)


def test_extract_eto_nearest_cell(tmp_path):
    path = tmp_path / "pet_2020.nc"
    _tiny_nc(str(path))
    values = extract_eto([str(path)], 36.81, -97.79, ["2020-06-01", "2020-06-02"])
    assert values["2020-06-01"] == 4.0
    assert values["2020-06-02"] == 13.0
