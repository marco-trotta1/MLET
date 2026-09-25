"""Check the Tier 1 physical-validity boundary."""
import importlib.util
from pathlib import Path

import pandas as pd

path = Path(__file__).resolve().parents[1] / "scripts/build_ml_tier1_cohort.py"
spec = importlib.util.spec_from_file_location("tier1_cohort", path)
tier1_cohort = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tier1_cohort)


def test_physical_validity_rejects_missing_and_impossible_weather() -> None:
    frame = pd.DataFrame(
        {
            "vp_kpa": [1.0, -0.1, 1.0, 1.0, None],
            "vpd_kpa": [1.0, 1.0, 3.0, 1.0, 1.0],
            "es_kpa": [2.0, 2.0, 2.0, 2.0, 2.0],
            "ws": [1.0, 1.0, 1.0, 76.0, 1.0],
            "t_avg": [10.0, 10.0, 10.0, 10.0, 10.0],
        }
    )

    flags = tier1_cohort.rule_flags(frame)

    assert flags.all(axis=1).tolist() == [True, False, False, False, False]
