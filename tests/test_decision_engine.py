from datetime import datetime, timezone

from app.decision_engine import TradingDecisionEngine
from app.domain import Quote, Side, Signal
from app.risk import AccountState


def quote() -> Quote:
    return Quote("EUR_USD", datetime.now(timezone.utc), 1.0999, 1.1001)


def account() -> AccountState:
    return AccountState(10000, 10000, 10000, 10000, 0, 0)


def test_approved_signal_becomes_paper_position():
    engine = TradingDecisionEngine()
    signal = Signal("EUR_USD", Side.BUY, 0.72, 0.75, 0.001, 1.0980, 1.1040)
    result = engine.process(signal, quote(), account(), value_per_price_unit=1.0)
    assert result.approved
    assert result.order is not None
    assert result.position is not None
    assert result.order.units > 0


def test_risk_limit_blocks_new_trade():
    engine = TradingDecisionEngine()
    blocked = AccountState(9700, 10000, 10000, 10000, 0, 0)
    signal = Signal("EUR_USD", Side.BUY, 0.72, 0.75, 0.001, 1.0980, 1.1040)
    result = engine.process(signal, quote(), blocked, value_per_price_unit=1.0)
    assert not result.approved
    assert "daily loss" in result.reason
