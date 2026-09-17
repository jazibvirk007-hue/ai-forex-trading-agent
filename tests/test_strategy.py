from app.domain import Side
from app.strategy import BaselineStrategy


def test_buy_signal_requires_edge_after_costs():
    strategy = BaselineStrategy()
    signal = strategy.generate("EUR_USD", 1.1000, 1.1010, 1.0990, 0.75, 0.0030, 0.0005)
    assert signal is not None
    assert signal.side is Side.BUY
    assert signal.stop_price < 1.1000 < signal.take_profit


def test_low_confidence_is_rejected():
    strategy = BaselineStrategy()
    assert strategy.generate("EUR_USD", 1.1, 1.101, 1.099, 0.50, 0.003, 0.0005) is None


def test_edge_below_cost_is_rejected():
    strategy = BaselineStrategy()
    assert strategy.generate("EUR_USD", 1.1, 1.101, 1.099, 0.8, 0.0005, 0.0005) is None
