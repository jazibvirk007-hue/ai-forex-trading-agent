from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression


class ProbabilityCalibrator:
    """Fit calibration only on a validation set; apply unchanged to OOS data."""

    def __init__(self) -> None:
        self._model: IsotonicRegression | None = None

    def fit(self, probability: pd.Series, outcome: pd.Series) -> "ProbabilityCalibrator":
        frame = pd.DataFrame({"p": probability, "y": outcome}).replace([np.inf, -np.inf], np.nan).dropna()
        if frame.empty or frame["y"].nunique() < 2:
            raise ValueError("calibration data must be non-empty and contain both classes")
        self._model = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        self._model.fit(frame["p"], frame["y"].astype(int))
        return self

    def transform(self, probability: pd.Series) -> pd.Series:
        if self._model is None:
            raise RuntimeError("calibrator is not fitted")
        values = probability.clip(0.0, 1.0)
        return pd.Series(self._model.predict(values.fillna(0.5)), index=probability.index)
