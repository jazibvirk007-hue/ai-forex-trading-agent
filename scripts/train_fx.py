from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import pandas as pd

from app.data.csv_provider import CSVDataProvider
from app.data.labels import triple_barrier_labels
from app.features.indicators import add_indicators
from app.ml.evaluation import evaluate_binary
from app.ml.model import FXClassifier, ModelConfig
from app.ml.training import train_walk_forward

FEATURES = [
    "return_1",
    "ema_20",
    "ema_50",
    "rsi_14",
    "atr_14",
    "bb_mid",
    "bb_upper",
    "bb_lower",
]


def build_dataset(path: str | Path) -> pd.DataFrame:
    frame = CSVDataProvider(path).load()
    frame = add_indicators(frame)
    frame["atr"] = frame["atr_14"]
    frame["label"] = triple_barrier_labels(
        frame,
        horizon=24,       # 2 hours on M5
        target_atr=1.5,
        stop_atr=1.0,
    )
    # Keep only resolved target-vs-stop outcomes. 1 = upward target first,
    # -1 = downward stop first. The model learns P(upward target wins).
    frame = frame[frame["label"].isin([-1.0, 1.0])].copy()
    frame["target"] = (frame["label"] == 1.0).astype(int)
    frame = frame.dropna(subset=FEATURES + ["target"]).reset_index(drop=True)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the EURUSD M5 FX model with chronological OOS validation.")
    parser.add_argument("--input", default="data/raw/EURUSD_M5_5Y_raw.csv")
    parser.add_argument("--output-dir", default="artifacts/eurusd_m5_5y")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    frame = build_dataset(args.input)
    if len(frame) < 100_000:
        raise ValueError(f"Expected a multi-year M5 dataset; only {len(frame):,} resolved rows are available")

    n = len(frame)
    train_size = int(n * 0.55)
    validation_size = int(n * 0.10)
    test_size = int(n * 0.10)

    config = ModelConfig(
        n_estimators=400,
        learning_rate=0.03,
        max_depth=6,
        num_leaves=31,
        random_state=42,
        min_probability=0.60,
    )

    results = train_walk_forward(
        frame,
        FEATURES,
        "target",
        train_size=train_size,
        validation_size=validation_size,
        test_size=test_size,
        model_config=config,
    )

    # Final untouched holdout: last 15% of the full five-year sample.
    final_cut = int(n * 0.85)
    development = frame.iloc[:final_cut]
    final_test = frame.iloc[final_cut:]

    final_model = FXClassifier(config)
    final_model.fit(development[FEATURES], development["target"])
    probabilities = final_model.predict_probability(final_test[FEATURES])
    final_metrics = evaluate_binary(final_test["target"], probabilities)

    with (out / "model.pkl").open("wb") as handle:
        pickle.dump(final_model, handle, protocol=pickle.HIGHEST_PROTOCOL)

    report = {
        "dataset": {
            "rows_after_labeling": int(n),
            "start": frame["timestamp"].min().isoformat(),
            "end": frame["timestamp"].max().isoformat(),
            "positive_rate": float(frame["target"].mean()),
        },
        "features": FEATURES,
        "label": {
            "horizon_bars": 24,
            "target_atr": 1.5,
            "stop_atr": 1.0,
        },
        "walk_forward": [
            {
                "fold": r.fold,
                "train_rows": r.train_rows,
                "validation_rows": r.validation_rows,
                "test_rows": r.test_rows,
                "validation": r.validation.__dict__,
                "test": r.test.__dict__,
            }
            for r in results
        ],
        "final_holdout": {
            "development_rows": int(len(development)),
            "test_rows": int(len(final_test)),
            "metrics": final_metrics.__dict__,
        },
    }
    (out / "training_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out / "feature_config.json").write_text(json.dumps(FEATURES, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2, default=str))
    print(f"Saved model: {(out / 'model.pkl').resolve()}")


if __name__ == "__main__":
    main()
