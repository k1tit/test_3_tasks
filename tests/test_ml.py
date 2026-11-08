import math
from datetime import date

from ml.features import FEATURE_COLUMNS, FORBIDDEN_COLUMNS, cycle
from ml.split import assign_split, split_bounds

AS_OF = date(2026, 10, 26)


def test_snapshot_windows_match_the_brief():
    train_start, test_start = split_bounds(AS_OF)
    assert train_start == date(2026, 7, 26)
    assert test_start == date(2026, 10, 5)


def test_boundary_dates_fall_into_one_split():
    assert assign_split(date(2026, 7, 25), AS_OF) == "ignore"
    assert assign_split(date(2026, 7, 26), AS_OF) == "train"
    assert assign_split(date(2026, 10, 4), AS_OF) == "train"
    assert assign_split(date(2026, 10, 5), AS_OF) == "test"
    assert assign_split(date(2026, 10, 26), AS_OF) == "test"
    assert assign_split(date(2026, 10, 27), AS_OF) == "future"


def test_features_do_not_include_the_target():
    assert set(FEATURE_COLUMNS).isdisjoint(FORBIDDEN_COLUMNS)


def test_cyclical_encoding_keeps_year_end_close():
    for value, period in ((12, 12), (7, 7), (365, 365.25)):
        sine, cosine = cycle(value, period)
        assert abs(sine ** 2 + cosine ** 2 - 1) < 1e-12
    new_year = cycle(1, 365.25)
    year_end = cycle(365, 365.25)
    mid_year = cycle(180, 365.25)

    def distance(left, right):
        return math.hypot(left[0] - right[0], left[1] - right[1])

    assert distance(new_year, year_end) < distance(new_year, mid_year)


def test_regression_metrics_on_a_perfect_forecast():
    pytest = __import__("pytest")
    pytest.importorskip("numpy")
    from ml.metrics import regression_metrics

    metrics = regression_metrics([100.0, 200.0, 400.0], [100.0, 200.0, 400.0])
    assert metrics["r2"] == 1
    assert metrics["mape_pct"] == 0
    assert metrics["rmse_rub"] == 0
    assert metrics["mae_rub"] == 0
