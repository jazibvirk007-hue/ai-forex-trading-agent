import numpy as np

from app.domain import Side
from app.strategies.registry import MarketSeries, StrategyRegistry


def test_trend_strategy_can_generate_buy_candidate():
    closes = np.linspace(1.08, 1.12, 120)
    highs = closes + 0.001
    lows = closes - 0.001
    market = MarketSeries(
        symbol="EURUSD",
        closes=tuple(closes),
        highs=tuple(highs),
        lows=tuple(lows),
        spread=0.00005,
    )
    results = StrategyRegistry().evaluate(market)
    assert results
    assert results[0].side is Side.BUY
    assert results[0].stop_distance > 0
    assert results[0].target_distance > results[0].stop_distance
