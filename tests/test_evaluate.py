import datetime

from mlet.evaluate import bias, blocked_bootstrap_mae_delta, field_withheld_folds, mae, rmse, time_split


def test_field_withheld_is_disjoint_and_covers_all():
    station_ids = [f"S{index}" for index in range(10)]
    folds = field_withheld_folds(station_ids, k=5, seed=1)
    assert len(folds) == 5
    for train, test in folds:
        assert set(train).isdisjoint(test)
        assert set(train) | set(test) == set(station_ids)
    assert set().union(*[set(test) for _train, test in folds]) == set(station_ids)


def test_field_withheld_is_deterministic():
    station_ids = [f"S{index}" for index in range(10)]
    assert field_withheld_folds(station_ids, 5, seed=42) == field_withheld_folds(station_ids, 5, seed=42)


def test_time_split_by_cutoff():
    train, test = time_split([datetime.date(2018, 12, 31), datetime.date(2019, 1, 1)], "2019-01-01")
    assert train == [0]
    assert test == [1]


def test_metrics():
    assert mae([1.0, -3.0]) == 2.0
    assert abs(rmse([3.0, 4.0]) - 3.5355339) < 1e-6
    assert bias([2.0, 2.0], [1.0, 1.0]) == 1.0


def test_blocked_bootstrap_ci_signs_when_a_is_worse():
    values = {f"S{index}": ([2.0] * 20, [1.0] * 20) for index in range(30)}
    delta, lower, upper = blocked_bootstrap_mae_delta(values, seed=7, iters=500)
    assert abs(delta - 1.0) < 1e-9
    assert lower > 0.0
    assert upper > 0.0
