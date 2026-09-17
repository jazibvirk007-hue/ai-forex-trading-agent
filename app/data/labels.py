from __future__ import annotations

import numpy as np
import pandas as pd


def triple_barrier_labels(
    frame: pd.DataFrame,
    horizon: int = 20,
    target_atr: float = 2.0,
    stop_atr: float = 1.0,
) -> pd.Series:
    """Create forward-looking research labels; features must use only prior/current data.

    1 = target reached first, -1 = stop reached first, 0 = neither/ambiguous.
    The last `horizon` rows are unlabeled (NaN) because their future window is incomplete.
    """
    if "close" not in frame or "atr" not in frame:
        raise ValueError("frame requires close and atr columns")
    close = frame["close"].to_numpy(dtype=float)
    atr = frame["atr"].to_numpy(dtype=float)
    labels = np.full(len(frame), np.nan)
    for i in range(max(0, len(frame) - horizon)):
        if not np.isfinite(close[i]) or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        upper = close[i] + target_atr * atr[i]
        lower = close[i] - stop_atr * atr[i]
        future = close[i + 1 : i + 1 + horizon]
        up = np.flatnonzero(future >= upper)
        down = np.flatnonzero(future <= lower)
        if len(up) and (not len(down) or up[0] < down[0]):
            labels[i] = 1
        elif len(down) and (not len(up) or down[0] < up[0]):
            labels[i] = -1
        elif len(up) and len(down):
            labels[i] = 0
        else:
            labels[i] = 0
    return pd.Series(labels, index=frame.index, name="label")
