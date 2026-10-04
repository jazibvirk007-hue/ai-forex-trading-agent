from datetime import datetime, timezone

from app.storage import TradingStore


def test_store_persists_risk_anchors_and_proposals(tmp_path):
    db = tmp_path / "trading.db"
    store = TradingStore(f"sqlite:///{db}")

    state = store.account_state(
        equity=100.0,
        open_positions=0,
        now=datetime(2026, 10, 5, 10, tzinfo=timezone.utc),
    )
    assert state.start_of_day_equity == 100.0
    assert state.peak_equity == 100.0

    state2 = store.account_state(
        equity=102.0,
        open_positions=0,
        now=datetime(2026, 10, 5, 12, tzinfo=timezone.utc),
    )
    assert state2.start_of_day_equity == 100.0
    assert state2.peak_equity == 102.0

    proposal_id = store.create_proposal(
        symbol="EURUSD",
        side="buy",
        volume_lots=0.01,
        reference_entry=1.1,
        stop_loss=1.095,
        take_profit=1.11,
        estimated_risk_cash=0.5,
        strategy="trend-momentum-v1",
        technical_confidence=0.7,
        ai_confidence=0.8,
        rationale="test",
    )
    proposal = store.proposal(proposal_id)
    assert proposal is not None
    assert proposal["status"] == "ready"

    store.set_proposal_status(proposal_id, "executed")
    assert store.proposal(proposal_id)["status"] == "executed"


def test_kill_switch_is_durable(tmp_path):
    store = TradingStore(f"sqlite:///{tmp_path / 'kill.db'}")
    assert not store.kill_switch()
    store.set_kill_switch(True, equity=50)
    assert store.kill_switch()
    store.set_kill_switch(False)
    assert not store.kill_switch()
