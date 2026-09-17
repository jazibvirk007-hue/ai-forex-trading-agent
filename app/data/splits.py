from __future__ import annotations

import pandas as pd


def walk_forward_splits(
    frame: pd.DataFrame,
    train_size: int,
    validation_size: int,
    test_size: int,
    step: int | None = None,
):
    """Yield chronological train/validation/test index ranges with no shuffling."""
    if min(train_size, validation_size, test_size) <= 0:
        raise ValueError("split sizes must be positive")
    step = step or test_size
    if step <= 0:
        raise ValueError("step must be positive")
    n = len(frame)
    start = 0
    while start + train_size + validation_size + test_size <= n:
        train = frame.iloc[start : start + train_size]
        validation = frame.iloc[start + train_size : start + train_size + validation_size]
        test_start = start + train_size + validation_size
        test = frame.iloc[test_start : test_start + test_size]
        yield train, validation, test
        start += step
