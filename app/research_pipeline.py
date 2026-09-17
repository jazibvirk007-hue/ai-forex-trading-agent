from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .backtest_engine import BacktestConfig, CostModel, EventDrivenBacktester
from .data.csv_provider import load_ohlcv_csv
from .features.indicators import add_indicators


@dataclass(frozen=True)
class ResearchReport:
    rows: int
    start: pd.Timestamp
    end: pd.Timestamp
    trades: int
    final_equity: float
    total_return: float


def prepare_csv(path: str | Path) -> pd.DataFrame:
    """Load OHLCV data and add causal indicators for research."""
    frame = load_ohlcv_csv(path)
    frame = add_indicators(frame)
    frame["atr"] = frame["atr_14"]
    return frame


def run_baseline(path: str | Path) -> ResearchReport:
    """Run the deterministic baseline backtest on a CSV containing OHLCV data.

    The `signal` column is intentionally required to be supplied by the strategy/model
    layer; this function does not manufacture a trading edge from future prices.
    """
    frame = prepare_csv(path)
    if "signal" not in frame:
        raise ValueError("CSV/research frame must contain a signal column before backtesting")
    config = BacktestConfig(cost=CostModel(spread_pips=1.0, slippage_pips=0.5))
    curve, trades = EventDrivenBacktester(config).run(frame)
    final_equity = float(curve["equity"].iloc[-1]) if not curve.empty else config.initial_equity
    total_return = final_equity / config.initial_equity - 1.0
    return ResearchReport(len(frame), frame["timestamp"].min(), frame["timestamp"].max(), len(trades), final_equity, total_return)
