import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_ml_tier1_gridmet_cohort import (
    gridmet_screen,
    join_gridmet_weather,
    sensor_fault_flags,
    source_weather,
)


def test_gridmet_screen_checks_daily_physical_bounds():
    frame = pd.DataFrame(
        {
            "t_min_c": [10.0, 10.0, 61.0, 10.0],
            "t_max_c": [20.0, 20.0, 62.0, 9.0],
            "vpd_kpa": [1.0, 3.0, 1.0, 1.0],
            "wind_m_s": [0.0, 3.0, 3.0, 76.0],
        }
    )

    flags = gridmet_screen(frame)

    assert flags.all(axis=1).tolist() == [True, False, False, False]


def test_missing_station_weather_is_not_a_known_fault():
    frame = pd.DataFrame(
        {
            "vp_kpa": [None, -0.1],
            "vpd_kpa_sensor": [None, None],
            "es_kpa": [None, None],
            "ws_sensor": [None, None],
            "t_avg_sensor": [None, None],
        }
    )

    flags = sensor_fault_flags(frame)

    assert flags.any(axis=1).tolist() == [False, True]


def test_source_weather_renames_archived_humidity_fields(tmp_path):
    source = tmp_path / "data/raw/flux_et/flux_ET_dataset/daily_data_files"
    source.mkdir(parents=True)
    pd.DataFrame(
        {
            "date": ["2020-01-01"],
            "t_avg": [20.0],
            "vpd": [1.2],
            "ws": [3.4],
            "vp": [1.1],
            "es": [2.3],
        }
    ).to_csv(source / "station-a_daily_data.csv", index=False)

    frame, hashes = source_weather(tmp_path, ["station-a"])

    assert frame.loc[0, ["vp_kpa", "vpd_kpa_sensor", "es_kpa"]].tolist() == [
        1.1,
        1.2,
        2.3,
    ]
    assert "station-a_daily_data.csv" in hashes


def test_gridmet_join_preserves_labeled_archive_values():
    joined = pd.DataFrame(
        {
            "site_id": ["station-a"],
            "date": ["2020-01-01"],
            "measured_et_mm": [4.0],
            "openet_et_mm": [3.0],
            "eto_mm": [5.0],
        }
    )
    weather = pd.DataFrame(
        {
            "site_id": ["station-a"],
            "date": ["2020-01-01"],
            "measured_et_mm": [99.0],
            "openet_et_mm": [98.0],
            "eto_mm": [97.0],
            "t_min_c": [10.0],
            "t_max_c": [20.0],
            "t_avg_c": [15.0],
            "vpd_kpa": [1.0],
            "wind_m_s": [3.0],
            "station_latitude": [40.0],
            "station_longitude": [-120.0],
        }
    )

    frame = join_gridmet_weather(joined, weather)

    assert frame.loc[0, "measured_et_mm"] == 4.0
    assert frame.loc[0, "openet_et_mm"] == 3.0
    assert frame.loc[0, "eto_mm"] == 5.0
    assert frame.loc[0, "t_avg_c"] == 15.0
    assert not any(name.endswith(("_x", "_y")) for name in frame.columns)
