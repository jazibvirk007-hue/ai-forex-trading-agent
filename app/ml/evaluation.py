from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score


@dataclass(frozen=True)
class ClassificationMetrics:
    samples: int
    accuracy: float
    roc_auc: float | None
    log_loss: float


def evaluate_binary(y_true: pd.Series, probability: pd.Series) -> ClassificationMetrics:
    frame = pd.DataFrame({"y": y_true, "p": probability}).replace([np.inf, -np.inf], np.nan).dropna()
    if frame.empty:
        raise ValueError("no valid observations")
    y = frame["y"].astype(int)
    p = frame["p"].clip(1e-6, 1 - 1e-6)
    predicted = (p >= 0.5).astype(int)
    auc = float(roc_auc_score(y, p)) if y.nunique() == 2 else None
    return ClassificationMetrics(
        samples=len(frame),
        accuracy=float(accuracy_score(y, predicted)),
        roc_auc=auc,
        log_loss=float(log_loss(y, p, labels=[0, 1])),
    )
