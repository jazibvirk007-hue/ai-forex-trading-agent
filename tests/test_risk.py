from app.risk import AccountState, RiskEngine, RiskLimits


def state(equity=10000, open_positions=0, correlated=0):
    return AccountState(equity, 10000, 10000, 10000, open_positions, correlated)


def test_position_size_respects_half_percent_risk():
    engine = RiskEngine(RiskLimits(risk_per_trade=0.005))
    units = engine.position_units(10000, 0.001, 1.0)
    assert units == 50000


def test_daily_loss_blocks_new_trade():
    engine = RiskEngine()
    decision = engine.check(state(equity=8000), 0.001, 1.0)
    assert not decision.approved
    assert "daily" in decision.reason


def test_position_limit_blocks_trade():
    engine = RiskEngine()
    decision = engine.check(state(open_positions=3), 0.001, 1.0)
    assert not decision.approved


def test_drawdown_halts_trading():
    engine = RiskEngine()
    decision = engine.check(AccountState(8900, 9300, 9300, 10000, 0, 0), 0.001, 1.0)
    assert not decision.approved
    assert "drawdown" in decision.reason
