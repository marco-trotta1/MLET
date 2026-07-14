import datetime

from mlet.loader import DailyRecord, SiteSeries, load_site_series


CSV = (
    "date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm\n"
    "2017-06-02,US-A32,4.8,5.4,,\n"
    "2017-06-01,US-A32,5.0,6.5,,5.1\n"
)


def test_load_site_series_sorts_and_flags(tmp_path):
    path = tmp_path / "US-A32.csv"
    path.write_text(CSV)
    series = load_site_series(str(path))
    assert isinstance(series, SiteSeries)
    assert series.site_id == "US-A32"
    assert [record.date for record in series.records] == [datetime.date(2017, 6, 1), datetime.date(2017, 6, 2)]
    assert isinstance(series.records[0], DailyRecord)
    assert len(series.labeled()) == 1
    assert series.label_ready is False


def test_label_ready_with_minimum_coverage(tmp_path):
    rows = ["date,site_id,openet_et_mm,eto_mm,ndvi,measured_et_mm"]
    for day in range(1, 32):
        rows.append(f"2017-07-{day:02d},S,5.0,6.0,,5.1")
    path = tmp_path / "S.csv"
    path.write_text("\n".join(rows) + "\n")
    assert load_site_series(str(path)).label_ready is True
