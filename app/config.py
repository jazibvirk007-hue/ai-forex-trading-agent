from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./trading.db"
    broker_mode: str = "paper"
    allow_live_trading: bool = False
    broker_name: str = "paper"
    broker_api_key: str | None = None
    broker_account_id: str | None = None

    risk_per_trade: float = 0.005
    max_daily_loss: float = 0.02
    max_weekly_loss: float = 0.05
    max_drawdown: float = 0.10
    max_open_positions: int = 3
    max_correlated_positions: int = 2

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
