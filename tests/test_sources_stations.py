from openpyxl import Workbook

from mlet.sources.stations import StationMeta, load_station_metadata


def _write(path: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Station ID", "General classification", "Data source/network", "Latitude", "Longitude"])
    sheet.append(["US-A32", "Grasslands", "AmeriFlux", 36.819268, -97.819772])
    sheet.append(["ALARC2_Smith6", "Croplands", "USDA", 33.07, -111.97])
    workbook.save(path)


def test_load_station_metadata(tmp_path):
    path = tmp_path / "meta.xlsx"
    _write(str(path))
    metadata = load_station_metadata(str(path))
    assert set(metadata) == {"US-A32", "ALARC2_Smith6"}
    station = metadata["US-A32"]
    assert isinstance(station, StationMeta)
    assert station.land_cover == "Grasslands"
    assert abs(station.latitude - 36.819268) < 1e-9
    assert metadata["ALARC2_Smith6"].longitude == -111.97
