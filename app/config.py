from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./trading.db"

    broker_mode: str = "live"
    broker_name: str = "mt5"
    allow_live_trading: bool = False
    live_trading_armed: bool = False
    autonomous_execution_enabled: bool = False

    mt5_terminal_path: str | None = None
    mt5_login: int | None = None
    mt5_password: str | None = None
    mt5_server: str | None = None
    mt5_deviation: int = 15
    mt5_magic: int = 560001

    risk_per_trade: float = 0.005
    max_daily_loss: float = 0.02
    max_weekly_loss: float = 0.05
    max_drawdown: float = 0.10
    max_open_positions: int = 1
    max_correlated_positions: int = 1
    correlation_threshold: float = 0.80

    engine_auto_start: bool = False
    engine_cycle_seconds: int = 30
    engine_symbols: str = "EURUSD,GBPUSD,USDJPY"
    engine_timeframe: str = "M5"
    engine_bars: int = 220
    min_ai_confidence: float = 0.66
    require_ai_consensus: bool = True
    min_seconds_between_trades: int = 900
    deal_sync_hours: int = 72
    reflection_enabled: bool = True

    ai_provider: str = "openai"
    ai_model: str | None = None
    ai_api_key: str | None = None
    ai_base_url: str | None = None

    research_feed_urls: str = ""
    fish_audio_model: str = "s2.1-pro"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
