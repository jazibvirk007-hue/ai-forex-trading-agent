import pandas as pd

from app.ml.dataset import build_training_frame


def bars(n: int = 80) -> pd.DataFrame:
    close = [1.1000 + i * 0.0001 for i in range(n)]
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC"),
        "open": close,
        "high": [value + 0.0002 for value in close],
        "low": [value - 0.0002 for value in close],
        "close": close,
        "volume": [1000] * n,
    })


def test_training_frame_has_binary_target_and_no_nan_features():
    frame, features = build_training_frame(bars(), horizon=5, target_atr=1.0, stop_atr=1.0)
    assert features
    assert frame[features].notna().all().all()
    assert frame["target"].dropna().isin([0, 1]).all()
    assert frame["barrier_label"].notna().all()


def test_training_frame_excludes_incomplete_future_labels():
    source = bars(30)
    frame, _ = build_training_frame(source, horizon=10)
    assert frame["timestamp"].max() < source["timestamp"].iloc[-10]
