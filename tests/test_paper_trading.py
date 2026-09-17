from datetime import datetime, timezone

from app.domain import OrderRequest, Quote, Side
from app.paper_account import PaperAccount
from app.paper_trading import PaperTradingEngine


def q(symbol: str, bid: float, ask: float) -> Quote:
    return Quote(symbol, datetime.now(timezone.utc), bid, ask)


def test_long_hits_stop_at_bid():
    engine = PaperTradingEngine()
    entry_quote = q("EUR_USD", 1.0999, 1.1001)
    order = OrderRequest("EUR_USD", Side.BUY, 1000, 1.1001, 1.0980, 1.1040)
    position = engine.open(order, entry_quote)
    closed = engine.update(q("EUR_USD", 1.0979, 1.0981))
    assert closed[0].position_id == position.position_id
    assert closed[0].reason == "stop_loss"
    assert closed[0].exit_price == 1.0979


def test_short_hits_target_at_ask():
    engine = PaperTradingEngine()
    entry_quote = q("EUR_USD", 1.0999, 1.1001)
    order = OrderRequest("EUR_USD", Side.SELL, 1000, 1.0999, 1.1020, 1.0960)
    engine.open(order, entry_quote)
    closed = engine.update(q("EUR_USD", 1.0959, 1.0960))
    assert closed[0].reason == "take_profit"
    assert closed[0].exit_price == 1.0960


def test_account_applies_realized_pnl():
    account = PaperAccount.create(10000)
    engine = PaperTradingEngine()
    order = OrderRequest("EUR_USD", Side.BUY, 1000, 1.1000, 1.0980, 1.1040)
    engine.open(order, q("EUR_USD", 1.0999, 1.1001))
    trade = engine.update(q("EUR_USD", 1.1041, 1.1043))[0]
    account.apply_closed_trade(trade)
    assert account.equity > 10000
