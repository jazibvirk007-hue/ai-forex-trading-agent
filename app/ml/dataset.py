from __future__ import annotations

import pandas as pd

from ..data.csv_provider import CSVDataProvider
from ..data.labels import triple_barrier_labels
from ..features.indicators import add_indicators

DEFAULT_FEATURES = [
    "return_1",
    "ema_20",
    "ema_50",
    "rsi_14",
    "atr_14",
    "bb_mid",
    "bb_upper",
    "bb_lower",
]


def build_training_frame(
    frame: pd.DataFrame,
    *,
    horizon: int = 20,
    target_atr: float = 2.0,
    stop_atr: float = 1.0,
    features: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Build a chronological supervised-learning frame.

    Indicators are causal. Labels are deliberately computed separately from the
    feature columns and use future bars only for the target. Rows with incomplete
    indicators or incomplete future labels are removed before model training.
    The binary target is 1 when the long-side target barrier wins and 0 otherwise.
    """
    required = {"open", "high", "low", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"frame requires columns: {missing}")

    enriched = add_indicators(frame)
    enriched["atr"] = enriched["atr_14"]
    enriched["barrier_label"] = triple_barrier_labels(
        enriched,
        horizon=horizon,
        target_atr=target_atr,
        stop_atr=stop_atr,
    )

    selected = list(features or DEFAULT_FEATURES)
    missing_features = [name for name in selected if name not in enriched.columns]
    if missing_features:
        raise ValueError(f"missing features: {missing_features}")

    enriched["target"] = (enriched["barrier_label"] == 1).astype("float")
    clean = enriched.dropna(subset=selected + ["barrier_label"]).copy()
    clean["target"] = clean["target"].astype(int)
    return clean, selected


def load_training_csv(
    path: str,
    **kwargs: object,
) -> tuple[pd.DataFrame, list[str]]:
    """Load a normalized OHLCV CSV and build its supervised training frame."""
    return build_training_frame(CSVDataProvider(path).load(), **kwargs)
