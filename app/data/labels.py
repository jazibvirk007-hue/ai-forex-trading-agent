from __future__ import annotations

import numpy as np
import pandas as pd


def triple_barrier_labels(
    frame: pd.DataFrame,
    horizon: int = 20,
    target_atr: float = 2.0,
    stop_atr: float = 1.0,
) -> pd.Series:
    """Create forward-looking triple-barrier labels without feature leakage.

    1 = target reached first, -1 = stop reached first, 0 = neither or both hit
    on the same future bar. The final `horizon` rows are NaN because their future
    window is incomplete. Bar highs/lows are used rather than closes so the labels
    represent actual intrabar barrier touches.
    """
    required = {"close", "high", "low", "atr"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"frame requires columns: {missing}")
    if horizon <= 0 or target_atr <= 0 or stop_atr <= 0:
        raise ValueError("horizon and ATR multipliers must be positive")

    close = frame["close"].to_numpy(dtype=float)
    high = frame["high"].to_numpy(dtype=float)
    low = frame["low"].to_numpy(dtype=float)
    atr = frame["atr"].to_numpy(dtype=float)
    labels = np.full(len(frame), np.nan)

    for i in range(max(0, len(frame) - horizon)):
        if not np.isfinite(close[i]) or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue

        upper = close[i] + target_atr * atr[i]
        lower = close[i] - stop_atr * atr[i]
        future_high = high[i + 1 : i + 1 + horizon]
        future_low = low[i + 1 : i + 1 + horizon]
        up = np.flatnonzero(future_high >= upper)
        down = np.flatnonzero(future_low <= lower)

        if len(up) and len(down):
            labels[i] = 0 if up[0] == down[0] else (1 if up[0] < down[0] else -1)
        elif len(up):
            labels[i] = 1
        elif len(down):
            labels[i] = -1
        else:
            labels[i] = 0

    return pd.Series(labels, index=frame.index, name="label")
