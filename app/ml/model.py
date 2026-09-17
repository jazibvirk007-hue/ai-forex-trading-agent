from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

try:
    from lightgbm import LGBMClassifier
except ImportError:  # pragma: no cover
    LGBMClassifier = None


@dataclass(frozen=True)
class ModelConfig:
    n_estimators: int = 300
    learning_rate: float = 0.03
    max_depth: int = 5
    num_leaves: int = 31
    random_state: int = 42
    min_probability: float = 0.60


class FXClassifier:
    """Leakage-safe wrapper around LightGBM for binary trade outcomes.

    The caller is responsible for chronological train/validation/test splitting.
    No shuffling is performed here.
    """

    def __init__(self, config: ModelConfig | None = None) -> None:
        self.config = config or ModelConfig()
        if LGBMClassifier is None:
            raise RuntimeError("LightGBM is required: install with `pip install -e '.[ml]'`")
        self.model: Any = LGBMClassifier(
            n_estimators=self.config.n_estimators,
            learning_rate=self.config.learning_rate,
            max_depth=self.config.max_depth,
            num_leaves=self.config.num_leaves,
            random_state=self.config.random_state,
            verbosity=-1,
        )
        self.feature_names: list[str] = []

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "FXClassifier":
        if len(X) != len(y) or len(X) == 0:
            raise ValueError("X and y must have the same non-zero length")
        if y.nunique(dropna=True) < 2:
            raise ValueError("training labels must contain both classes")
        clean = X.replace([np.inf, -np.inf], np.nan)
        valid = clean.notna().all(axis=1) & y.notna()
        self.feature_names = list(X.columns)
        self.model.fit(clean.loc[valid, self.feature_names], y.loc[valid].astype(int))
        return self

    def predict_probability(self, X: pd.DataFrame) -> pd.Series:
        if not self.feature_names:
            raise RuntimeError("model is not fitted")
        clean = X.replace([np.inf, -np.inf], np.nan)
        probabilities = pd.Series(np.nan, index=X.index, dtype=float)
        valid = clean[self.feature_names].notna().all(axis=1)
        if valid.any():
            probabilities.loc[valid] = self.model.predict_proba(
                clean.loc[valid, self.feature_names]
            )[:, 1]
        return probabilities

    def predict_signal(self, X: pd.DataFrame) -> pd.Series:
        probability = self.predict_probability(X)
        return (probability >= self.config.min_probability).astype("Int64")
