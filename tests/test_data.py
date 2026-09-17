import pandas as pd
import pytest

from app.data.csv_provider import CSVDataProvider
from app.data.labels import triple_barrier_labels
from app.data.splits import walk_forward_splits


def test_csv_provider_normalizes_datetime_alias_and_sorts(tmp_path):
    path = tmp_path / "bars.csv"
    pd.DataFrame([
        ["2026-01-01T00:01:00Z", 1.1, 1.2, 1.0, 1.15, 10],
        ["2026-01-01T00:00:00Z", 1.0, 1.1, 0.9, 1.05, 8],
    ], columns=["datetime", "open", "high", "low", "close", "volume"]).to_csv(path, index=False)
    result = CSVDataProvider(path).load()
    assert result["timestamp"].is_monotonic_increasing
    assert result.loc[0, "close"] == 1.05


def test_csv_provider_rejects_missing_columns(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"timestamp": ["2026-01-01"], "close": [1.0]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="missing required columns"):
        CSVDataProvider(path).load()


def test_labels_do_not_fill_incomplete_future_window():
    frame = pd.DataFrame({
        "close": [100, 102, 104, 106],
        "high": [100, 103, 105, 107],
        "low": [100, 101, 103, 105],
        "atr": [1, 1, 1, 1],
    })
    labels = triple_barrier_labels(frame, horizon=2, target_atr=1, stop_atr=1)
    assert labels.iloc[-2:].isna().all()
    assert labels.iloc[0] == 1


def test_labels_mark_same_bar_barrier_hits_ambiguous():
    frame = pd.DataFrame({
        "close": [100, 100, 100, 100],
        "high": [100, 102, 101, 101],
        "low": [100, 98, 99, 99],
        "atr": [1, 1, 1, 1],
    })
    labels = triple_barrier_labels(frame, horizon=2, target_atr=1, stop_atr=1)
    assert labels.iloc[0] == 0


def test_walk_forward_is_chronological():
    frame = pd.DataFrame({"x": range(10)})
    splits = list(walk_forward_splits(frame, 4, 2, 2, step=2))
    assert len(splits) == 2
    train, validation, test = splits[0]
    assert list(train.x) == [0, 1, 2, 3]
    assert list(validation.x) == [4, 5]
    assert list(test.x) == [6, 7]
    train2, validation2, test2 = splits[1]
    assert list(train2.x) == [2, 3, 4, 5]
    assert list(validation2.x) == [6, 7]
    assert list(test2.x) == [8, 9]
