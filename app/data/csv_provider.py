from __future__ import annotations

from pathlib import Path
import pandas as pd

REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


class CSVDataProvider:
    """Load and validate normalized OHLCV data from CSV for reproducible research."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> pd.DataFrame:
        frame = pd.read_csv(self.path)

        # Public FX datasets commonly call the bar-open timestamp `datetime`.
        if "timestamp" not in frame.columns and "datetime" in frame.columns:
            frame = frame.rename(columns={"datetime": "timestamp"})

        missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"missing required columns: {missing}")

        frame = frame[list(REQUIRED_COLUMNS)].copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        for column in REQUIRED_COLUMNS[1:]:
            frame[column] = pd.to_numeric(frame[column], errors="raise")

        if frame["timestamp"].duplicated().any():
            raise ValueError("duplicate timestamps are not allowed")
        if not frame["timestamp"].is_monotonic_increasing:
            frame = frame.sort_values("timestamp")

        invalid_ohlc = (
            (frame["high"] < frame[["open", "close"]].max(axis=1))
            | (frame["low"] > frame[["open", "close"]].min(axis=1))
            | (frame["low"] <= 0)
            | (frame["high"] <= 0)
            | (frame["open"] <= 0)
            | (frame["close"] <= 0)
            | (frame["volume"] < 0)
        )
        if invalid_ohlc.any():
            raise ValueError("invalid OHLCV rows detected")

        return frame.reset_index(drop=True)
