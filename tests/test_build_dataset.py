import csv
import json

from openpyxl import Workbook

from mlet.build_dataset import BuildStats, build_dataset
from mlet.validator import validate_csv


def _metadata(path: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Station ID", "General classification", "Data source/network", "Latitude", "Longitude"])
    sheet.append(["US-A32", "Grasslands", "AmeriFlux", 36.8, -97.8])
    workbook.save(path)


def test_build_dataset_writes_validator_gated_contract_and_covariates(tmp_path):
    metadata = tmp_path / "metadata.xlsx"
    _metadata(str(metadata))
    openet = tmp_path / "daily_data.dat"
    openet.write_text(
        "Site ID\tEnsemble\tDATE\n"
        "US-A32\t5.0\t2017-06-01\n"
        "US-A32\t4.8\t2017-06-02\n"
        "US-A32\t4.5\t2017-06-03\n"
    )
    flux_dir = tmp_path / "flux"
    flux_dir.mkdir()
    (flux_dir / "US-A32_daily_data.csv").write_text(
        "date,ET_corr,ET_gap,gridMET_ETo,t_avg,vpd,ws,ppt\n"
        "2017-06-01,5.1,False,6.5,24,1.8,2.1,0\n"
        "2017-06-02,,True,5.4,23,1.5,1.9,0\n"
        "2017-06-03,4.6,False,6.0,25,1.9,2.0,0\n"
    )
    output = tmp_path / "interim"

    stats = build_dataset(str(openet), str(flux_dir), str(metadata), str(output))

    assert isinstance(stats, BuildStats)
    assert stats.stations == 1
    assert stats.rows_written == 3
    assert stats.labeled_rows == 2
    assert stats.dropped_gap == 1
    written = output / "US-A32.csv"
    assert validate_csv(str(written)).is_valid
    rows = list(csv.DictReader(written.open()))
    assert rows[0]["openet_et_mm"] == "5.0"
    assert rows[0]["eto_mm"] == "6.5"
    assert rows[0]["measured_et_mm"] == "5.1"
    assert rows[1]["measured_et_mm"] == ""
    covariates = json.loads((output / "_weather.json").read_text())
    assert covariates["US-A32"]["2017-06-01"] == {"t_avg": 24.0, "vpd": 1.8, "ws": 2.1, "ppt": 0.0}
