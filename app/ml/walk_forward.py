from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Fold:
    train: pd.Index
    validation: pd.Index
    test: pd.Index


def make_folds(
    frame: pd.DataFrame,
    train_size: int,
    validation_size: int,
    test_size: int,
    step: int | None = None,
) -> list[Fold]:
    """Create chronological, non-overlapping evaluation folds."""
    if min(train_size, validation_size, test_size) <= 0:
        raise ValueError("fold sizes must be positive")
    step = step or test_size
    if step <= 0:
        raise ValueError("step must be positive")

    folds: list[Fold] = []
    start = 0
    n = len(frame)
    while start + train_size + validation_size + test_size <= n:
        a = start + train_size
        b = a + validation_size
        c = b + test_size
        folds.append(Fold(frame.index[start:a], frame.index[a:b], frame.index[b:c]))
        start += step
    return folds
