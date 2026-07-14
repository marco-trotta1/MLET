import math

from mlet.baselines import CropCoefficient, OpenETDirect, OpenETRecal, OpenETRidge, Persistence, WeatherRidge


def _sample(openet: float, eto: float, y: float, t_avg: float = 20.0, vpd: float = 1.5, ws: float = 2.0, doy: int = 150) -> dict[str, float]:
    return {
        "openet": openet,
        "eto": eto,
        "y": y,
        "t_avg": t_avg,
        "vpd": vpd,
        "ws": ws,
        "doy_sin": math.sin(2 * math.pi * doy / 365),
        "doy_cos": math.cos(2 * math.pi * doy / 365),
    }


def test_persistence_uses_previous_day_truth():
    assert Persistence().predict_series([5.0, 4.8, 4.5]) == [None, 5.0, 4.8]


def test_crop_coefficient_recovers_constant_ratio():
    model = CropCoefficient()
    model.fit([_sample(0, 5.0, 3.0), _sample(0, 10.0, 6.0)])
    assert abs(model.predict(_sample(0, 8.0, 0)) - 4.8) < 1e-9


def test_openet_direct_is_identity():
    assert OpenETDirect().predict(_sample(4.2, 5.0, 0.0)) == 4.2


def test_openet_recal_removes_linear_bias():
    model = OpenETRecal()
    model.fit([_sample(value, 5.0, 2 * value + 1) for value in (1.0, 2.0, 3.0, 4.0)])
    assert abs(model.predict(_sample(5.0, 5.0, 0.0)) - 11.0) < 1e-6


def test_openet_ridge_beats_direct_on_biased_data():
    training = [_sample(value, value + 1, 2 * value) for value in range(1, 40)]
    model = OpenETRidge()
    model.fit(training)
    assert abs(model.predict(_sample(20.0, 21.0, 0.0)) - 40.0) < 5.0


def test_weather_ridge_fits_when_a_feature_is_constant():
    model = WeatherRidge()
    model.fit([_sample(0.0, value, 0.5 * value) for value in range(1, 20)])
    assert abs(model.predict(_sample(0.0, 20.0, 0.0)) - 10.0) < 2.0
