from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MonteCarloSummary:
    simulations: int
    median_return: float
    worst_return: float
    median_max_drawdown: float
    worst_max_drawdown: float


def simulate_returns(
    trade_returns: np.ndarray,
    simulations: int = 1000,
    seed: int = 42,
) -> MonteCarloSummary:
    """Bootstrap trade returns to estimate path sensitivity.

    This is a robustness diagnostic, not a forecast of future performance.
    """
    values = np.asarray(trade_returns, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0 or simulations <= 0:
        raise ValueError("trade_returns must be non-empty and simulations must be positive")

    rng = np.random.default_rng(seed)
    returns: list[float] = []
    drawdowns: list[float] = []
    for _ in range(simulations):
        sample = rng.choice(values, size=len(values), replace=True)
        equity = np.cumprod(1.0 + sample)
        peak = np.maximum.accumulate(equity)
        dd = 1.0 - equity / peak
        returns.append(float(equity[-1] - 1.0))
        drawdowns.append(float(dd.max()))

    return MonteCarloSummary(
        simulations=simulations,
        median_return=float(np.median(returns)),
        worst_return=float(np.min(returns)),
        median_max_drawdown=float(np.median(drawdowns)),
        worst_max_drawdown=float(np.max(drawdowns)),
    )
