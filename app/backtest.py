from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    equity: pd.Series
    total_return: float
    max_drawdown: float
    sharpe: float
    sortino: float
    win_rate: float
    profit_factor: float
    expectancy: float


def summarize_equity(equity: pd.Series, periods_per_year: int = 252) -> BacktestResult:
    equity = equity.astype(float).dropna()
    returns = equity.pct_change().dropna()
    if equity.empty:
        raise ValueError("equity curve is empty")
    peak = equity.cummax()
    drawdown = equity / peak - 1
    downside = returns[returns < 0]
    sharpe = float(np.sqrt(periods_per_year) * returns.mean() / returns.std()) if returns.std() else 0.0
    sortino = float(np.sqrt(periods_per_year) * returns.mean() / downside.std()) if downside.std() else 0.0
    gains = returns[returns > 0].sum()
    losses = -returns[returns < 0].sum()
    profit_factor = float(gains / losses) if losses else float("inf")
    return BacktestResult(
        equity=equity,
        total_return=float(equity.iloc[-1] / equity.iloc[0] - 1),
        max_drawdown=float(-drawdown.min()),
        sharpe=sharpe,
        sortino=sortino,
        win_rate=float((returns > 0).mean()) if len(returns) else 0.0,
        profit_factor=profit_factor,
        expectancy=float(returns.mean()) if len(returns) else 0.0,
    )
