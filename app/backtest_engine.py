from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    spread_pips: float = 1.0
    slippage_pips: float = 0.0
    commission_per_unit: float = 0.0
    pip_size: float = 0.0001

    def round_trip_price_cost(self) -> float:
        return 2.0 * (self.spread_pips + self.slippage_pips) * self.pip_size


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float = 10_000.0
    risk_per_trade: float = 0.005
    stop_pips: float = 20.0
    reward_risk: float = 1.5
    cost: CostModel = CostModel()


@dataclass(frozen=True)
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: int
    entry: float
    exit: float
    pnl: float
    reason: str


class EventDrivenBacktester:
    """Small deterministic baseline backtester.

    `signal` must be -1, 0, or +1 and is interpreted at the next bar's open.
    This intentionally avoids same-bar look-ahead.
    """

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(self, bars: pd.DataFrame) -> tuple[pd.DataFrame, list[Trade]]:
        required = {"timestamp", "open", "high", "low", "close", "signal"}
        missing = required - set(bars.columns)
        if missing:
            raise ValueError(f"missing columns: {sorted(missing)}")
        if len(bars) < 2:
            return bars.copy(), []

        data = bars.sort_values("timestamp").reset_index(drop=True).copy()
        equity = self.config.initial_equity
        equity_curve = []
        trades: list[Trade] = []
        position = None

        for i in range(len(data)):
            row = data.iloc[i]
            timestamp = row["timestamp"]

            if position is not None:
                hit = False
                exit_price = float(row["close"])
                reason = "signal"
                if position["side"] == 1:
                    if row["low"] <= position["stop"]:
                        exit_price, reason, hit = position["stop"], "stop", True
                    elif row["high"] >= position["target"]:
                        exit_price, reason, hit = position["target"], "target", True
                else:
                    if row["high"] >= position["stop"]:
                        exit_price, reason, hit = position["stop"], "stop", True
                    elif row["low"] <= position["target"]:
                        exit_price, reason, hit = position["target"], "target", True

                opposite = int(row["signal"]) == -position["side"]
                if hit or opposite or i == len(data) - 1:
                    gross = (exit_price - position["entry"]) * position["units"] * position["side"]
                    commission = self.config.cost.commission_per_unit * position["units"] * 2
                    pnl = gross - commission
                    equity += pnl
                    trades.append(Trade(position["entry_time"], timestamp, position["side"], position["entry"], exit_price, pnl, reason))
                    position = None

            if position is None and i + 1 < len(data):
                signal = int(row["signal"])
                if signal in (-1, 1):
                    entry_row = data.iloc[i + 1]
                    entry = float(entry_row["open"])
                    pip = self.config.cost.pip_size
                    stop_distance = self.config.stop_pips * pip
                    target_distance = stop_distance * self.config.reward_risk
                    risk_cash = equity * self.config.risk_per_trade
                    units = risk_cash / stop_distance
                    entry += signal * (self.config.cost.spread_pips + self.config.cost.slippage_pips) * pip
                    stop = entry - signal * stop_distance
                    target = entry + signal * target_distance
                    position = {"side": signal, "entry": entry, "entry_time": entry_row["timestamp"], "stop": stop, "target": target, "units": units}

            equity_curve.append((timestamp, equity))

        curve = pd.DataFrame(equity_curve, columns=["timestamp", "equity"])
        curve["return"] = curve["equity"].pct_change().fillna(0.0)
        return curve, trades
