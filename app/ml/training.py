from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path

import pandas as pd

from .evaluation import ClassificationMetrics, evaluate_binary
from .model import FXClassifier, ModelConfig
from .walk_forward import make_folds


@dataclass(frozen=True)
class FoldResult:
    fold: int
    train_rows: int
    validation_rows: int
    test_rows: int
    validation: ClassificationMetrics
    test: ClassificationMetrics


def train_walk_forward(
    frame: pd.DataFrame,
    features: list[str],
    target: str,
    train_size: int,
    validation_size: int,
    test_size: int,
    model_config: ModelConfig | None = None,
) -> list[FoldResult]:
    """Train independently on each chronological fold and report OOS metrics."""
    missing = [c for c in features + [target] if c not in frame.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")

    folds = make_folds(frame, train_size, validation_size, test_size)
    results: list[FoldResult] = []
    for number, fold in enumerate(folds, start=1):
        train = frame.loc[fold.train]
        validation = frame.loc[fold.validation]
        test = frame.loc[fold.test]
        model = FXClassifier(model_config)
        model.fit(train[features], train[target])
        val_metrics = evaluate_binary(validation[target], model.predict_probability(validation[features]))
        test_metrics = evaluate_binary(test[target], model.predict_probability(test[features]))
        results.append(FoldResult(number, len(train), len(validation), len(test), val_metrics, test_metrics))
    return results


def save_results(results: list[FoldResult], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps([asdict(result) for result in results], indent=2, default=lambda x: x),
        encoding="utf-8",
    )
