import datetime
import json
import math

import numpy as np
import xarray as xr
from openpyxl import Workbook

from mlet.cli import main
from mlet.experiments.phase2_openet_value import run


def _write_interim(directory) -> None:
    start = datetime.date(2018, 12, 15)
    weather: dict[str, dict[str, dict[str, float]]] = {}
    for station, ratio in (("S1", 0.60), ("S2", 0.62)):
        rows = ["date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm"]
        station_weather: dict[str, dict[str, float]] = {}
        for offset in range(50):
            date = start + datetime.timedelta(days=offset)
            eto = 5.0 + (offset % 5) * 0.5
            target = round(ratio * eto, 3)
            rows.append(f"{date},{station},{target + 0.3},{eto},,{target}")
            station_weather[date.isoformat()] = {"t_avg": 20.0, "vpd": 1.5, "ws": 2.0, "ppt": 0.0}
        (directory / f"{station}.csv").write_text("\n".join(rows) + "\n")
        weather[station] = station_weather
    (directory / "_landcover.json").write_text(json.dumps({"S1": "Croplands", "S2": "Grasslands"}))
    (directory / "_weather.json").write_text(json.dumps(weather))


def test_evaluate_writes_report_with_decision_and_strata(tmp_path, capsys):
    interim = tmp_path / "interim"
    interim.mkdir()
    _write_interim(interim)
    report = tmp_path / "results.md"
    result = main(["evaluate", "--interim", str(interim), "--landcover", str(interim / "_landcover.json"), "--out", str(report)])
    assert result == 0
    text = report.read_text()
    assert "OpenET-value decision" in text
    assert "Field-withheld" in text
    assert "Croplands" in text
    assert "B0_Persistence" in text
    assert "decision" in capsys.readouterr().out.lower()


def test_qc_gridmet_prints_mean_absolute_delta(tmp_path, capsys):
    interim = tmp_path / "interim"
    interim.mkdir()
    (interim / "S1.csv").write_text(
        "date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm\n"
        "2020-06-01,S1,4.0,4.0,,3.9\n"
    )
    metadata = tmp_path / "metadata.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Station ID", "General classification", "Data source/network", "Latitude", "Longitude"])
    sheet.append(["S1", "Croplands", "test", 36.8, -97.8])
    workbook.save(metadata)
    gridmet = tmp_path / "gridmet"
    gridmet.mkdir()
    dataset = xr.Dataset(
        {"potential_evapotranspiration": (("day", "lat", "lon"), np.array([[[4.0]]]))},
        coords={"day": np.array(["2020-06-01"], dtype="datetime64[ns]"), "lat": [36.8], "lon": [-97.8]},
    )
    dataset.to_netcdf(gridmet / "pet_2020.nc")
    result = main(["qc-gridmet", "--interim", str(interim), "--gridmet-dir", str(gridmet), "--metadata", str(metadata), "--n", "1"])
    assert result == 0
    assert "mean_abs_delta_mm=0.000" in capsys.readouterr().out


def test_time_withheld_models_do_not_fit_post_cutoff_targets(tmp_path):
    interim = tmp_path / "interim"
    interim.mkdir()
    weather: dict[str, dict[str, dict[str, float]]] = {}
    for station in ("S1", "S2"):
        (interim / f"{station}.csv").write_text(
            "date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm\n"
            f"2018-12-31,{station},5.0,5.0,,5.0\n"
            f"2019-01-01,{station},5.0,5.0,,500.0\n"
        )
        weather[station] = {
            "2018-12-31": {"t_avg": 20.0, "vpd": 1.5, "ws": 2.0, "ppt": 0.0},
            "2019-01-01": {"t_avg": 20.0, "vpd": 1.5, "ws": 2.0, "ppt": 0.0},
        }
    (interim / "_weather.json").write_text(json.dumps(weather))
    landcover = interim / "_landcover.json"
    landcover.write_text(json.dumps({"S1": "Croplands", "S2": "Croplands"}))
    result = run(str(interim), str(landcover))
    time = result["time_withheld"]
    assert isinstance(time, dict)
    models = time["models"]
    assert isinstance(models, dict)
    assert float(models["B1_CropCoefficient"]["mae"]) > 400.0


def test_field_withheld_report_keeps_signed_model_bias(tmp_path):
    interim = tmp_path / "interim"
    interim.mkdir()
    weather: dict[str, dict[str, dict[str, float]]] = {}
    for station in ("S1", "S2"):
        (interim / f"{station}.csv").write_text(
            "date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm\n"
            f"2018-06-01,{station},5.0,5.0,,3.0\n"
            f"2018-06-02,{station},5.0,5.0,,3.0\n"
        )
        weather[station] = {
            "2018-06-01": {"t_avg": 20.0, "vpd": 1.5, "ws": 2.0, "ppt": 0.0},
            "2018-06-02": {"t_avg": 20.0, "vpd": 1.5, "ws": 2.0, "ppt": 0.0},
        }
    (interim / "_weather.json").write_text(json.dumps(weather))
    landcover = interim / "_landcover.json"
    landcover.write_text(json.dumps({"S1": "Croplands", "S2": "Grasslands"}))

    result = run(str(interim), str(landcover))

    field = result["field_withheld"]
    assert isinstance(field, dict)
    models = field["models"]
    assert isinstance(models, dict)
    assert float(models["M1_OpenETDirect"]["bias"]) == 2.0


def test_evaluation_excludes_nonfinite_weather_covariates(tmp_path):
    interim = tmp_path / "interim"
    interim.mkdir()
    _write_interim(interim)
    weather_path = interim / "_weather.json"
    weather = json.loads(weather_path.read_text())
    weather["S1"]["2018-12-15"]["vpd"] = float("inf")
    weather_path.write_text(json.dumps(weather))

    result = run(str(interim), str(interim / "_landcover.json"))

    field = result["field_withheld"]
    assert isinstance(field, dict)
    models = field["models"]
    assert isinstance(models, dict)
    assert math.isfinite(float(models["B2_WeatherRidge"]["mae"]))
    assert math.isfinite(float(models["M3_OpenETRidge"]["mae"]))
