from app.config import Settings
from app.engine import LiveAnalysisEngine


def test_engine_is_confirmed_live_and_does_not_require_mt5_to_construct(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'engine.db'}",
        require_ai_consensus=False,
        engine_symbols="EURUSD",
    )
    engine = LiveAnalysisEngine(settings)
    status = engine.status()
    assert status["execution_mode"] == "confirmed-live"
    assert status["symbols"] == ["EURUSD"]
    assert not status["running"]
