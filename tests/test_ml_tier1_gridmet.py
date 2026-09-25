import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ml_tier1_gridmet as runner


class FeatureNetwork:
    def predict(self, inputs):
        wind = inputs[:, -1]
        return wind, wind + 10, wind + 20, np.column_stack([wind, wind, wind])


def test_augmented_selector_features_use_faulted_input_predictions(monkeypatch):
    columns = ["openet", "eto", "doy_sin", "doy_cos", "t_avg", "vpd", "ws"]
    train = pd.DataFrame(
        {
            "row_id": [0, 1, 2],
            "station": ["a", "b", "c"],
            "group": ["a", "b", "c"],
            "date": pd.to_datetime(["2010-01-01", "2010-01-02", "2010-01-03"]),
            "y": [3.0, 4.0, 5.0],
            "openet": [2.0, 3.0, 4.0],
            "eto": [4.0, 5.0, 6.0],
            "doy_sin": [0.0, 0.0, 0.0],
            "doy_cos": [1.0, 1.0, 1.0],
            "t_avg": [20.0, 21.0, 22.0],
            "vpd": [1.0, 1.0, 1.0],
            "ws": [1.0, 2.0, 1.0],
        }
    )
    split = {
        "fold": 2012,
        "inner_partitions": [
            {"train_row_ids": [0, 1], "validation_row_ids": [2]}
        ],
    }

    monkeypatch.setattr(
        runner,
        "fit_gridmet_ensemble",
        lambda inputs, residual: (FeatureNetwork(), {}),
    )

    def fault_inputs(frame, inputs, training, feature_columns):
        corrupted = inputs.copy()
        corrupted[:, feature_columns.index("ws")] = 10.0
        return {"clean": inputs.copy(), "corrupted": corrupted}

    monkeypatch.setattr(runner.tier1, "fault_inputs", fault_inputs)

    _, augmented, _ = runner.inner_training(train, split, columns)

    features = augmented[0][0]
    np.testing.assert_allclose(features[0, :4], [10.0, 10.0, 20.0, np.log1p(30.0)])


def test_gridmet_ensemble_fits_ten_declared_seeds(monkeypatch):
    fitted_seeds = []

    class FakeMLP:
        def __init__(self, *, random_state, **kwargs):
            fitted_seeds.append(random_state)

        def fit(self, inputs, target):
            self.n_iter_ = 1
            self.loss_ = 0.0
            return self

    monkeypatch.setattr(runner, "MLPRegressor", FakeMLP)
    inputs = np.arange(42, dtype=float).reshape(6, 7)
    residual = np.arange(6, dtype=float)

    network, record = runner.fit_gridmet_ensemble(inputs, residual)

    assert len(network.models) == 10
    assert fitted_seeds == runner.NEURAL_SEEDS
    assert [item["seed"] for item in record["seeds"]] == runner.NEURAL_SEEDS
