from __future__ import annotations

import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add causal indicators. Input requires open/high/low/close columns."""
    out = df.copy().sort_index()
    close = out["close"]
    high, low = out["high"], out["low"]

    out["return_1"] = close.pct_change()
    out["ema_20"] = close.ewm(span=20, adjust=False).mean()
    out["ema_50"] = close.ewm(span=50, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    out["rsi_14"] = 100 - (100 / (1 + rs))
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    out["atr_14"] = tr.rolling(14).mean()
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    out["bb_mid"] = mid
    out["bb_upper"] = mid + 2 * std
    out["bb_lower"] = mid - 2 * std
    return out
