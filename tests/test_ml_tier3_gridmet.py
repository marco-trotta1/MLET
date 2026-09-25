import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ml_tier3_gridmet as tier3


def test_tier3_reads_the_frozen_tier1_cohort():
    assert tier3.COHORT.is_file()


def test_conformal_offset_uses_finite_sample_group_rank():
    scores = np.array([4.0, 1.0, 3.0, 2.0])

    offset = tier3.conformal_offset(scores, alpha=0.2)
    shuffled_offset = tier3.conformal_offset(scores[[2, 0, 3, 1]], alpha=0.2)

    assert offset == 4.0
    assert shuffled_offset == offset


def test_interval_threshold_minimizes_macro_error_then_maximizes_acceptance():
    frame = pd.DataFrame(
        {
            "station": ["a", "b"],
            "openet": [1.0, 0.0],
            "correction": [-1.0, 1.0],
            "y": [0.0, 0.0],
        }
    )

    threshold, risk, coverage = tier3.select_interval_threshold(
        frame, np.array([1.0, 2.0])
    )

    assert threshold == 1.0
    assert risk == 0.0
    assert coverage == 0.5


def test_conformal_selector_uses_disjoint_spatial_groups():
    rows = 60
    frame = pd.DataFrame(
        {
            "row_id": np.arange(rows),
            "group": [f"g{index}" for index in range(rows)],
            "station": [f"s{index}" for index in range(rows)],
            "openet": np.full(rows, 2.0),
            "eto": np.full(rows, 3.0),
            "doy_sin": np.zeros(rows),
            "doy_cos": np.ones(rows),
            "t_avg": np.full(rows, 20.0),
            "vpd": np.full(rows, 1.0),
            "ws": np.full(rows, 2.0),
            "correction": np.full(rows, 0.5),
            "spread": np.full(rows, 0.1),
            "distance": np.full(rows, 1.0),
            "y": np.full(rows, 3.2),
        }
    )

    _, record = tier3.fit_conformal_selector(frame, seed=20260924)

    assert record["fit_rows"] + record["calibration_rows"] + record["threshold_rows"] == rows
    assert record["calibration_group_count"] == 20
    assert np.isfinite(record["offset"])
