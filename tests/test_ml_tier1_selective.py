"""Check the Tier 1 fault transformations."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

path = Path(__file__).resolve().parents[1] / "scripts/ml_tier1_selective.py"
spec = importlib.util.spec_from_file_location("tier1_selective", path)
tier1_selective = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tier1_selective)


def test_faults_keep_clean_inputs_and_apply_declared_unit_changes() -> None:
    columns = tier1_selective.FEATURES
    values = np.ones((8, len(columns)))
    values[:, columns.index("t_avg")] = 10
    values[:, columns.index("ws")] = np.arange(1, 9)
    frame = pd.DataFrame(
        {
            "station": ["a"] * 8,
            "date": pd.date_range("2020-01-01", periods=8).strftime("%Y-%m-%d"),
        }
    )
    training = pd.DataFrame(
        {"station": ["b", "b"], "date": ["2019-01-01", "2019-01-02"], "ws": [2.0, 4.0]}
    )

    faults = tier1_selective.fault_inputs(frame, values, training, columns)

    np.testing.assert_array_equal(faults["clean"], values)
    assert faults["wind_x0"][:, columns.index("ws")].tolist() == [0.0] * 8
    assert faults["wind_stuck_7_days"][:, columns.index("ws")].tolist() == [1.0] * 7 + [8.0]
    assert faults["wind_dropout_median"][:, columns.index("ws")].tolist() == [3.0] * 8
    assert faults["temperature_fahrenheit_as_celsius"][0, columns.index("t_avg")] == 50
    assert faults["vpd_x10"][0, columns.index("vpd")] == 10
