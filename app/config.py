from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./trading.db"

    # The product is live-first. Execution still requires both explicit arm flags.
    broker_mode: str = "live"
    broker_name: str = "mt5"
    allow_live_trading: bool = False
    live_trading_armed: bool = False

    # MT5 can use a terminal that is already signed in. These values are optional.
    mt5_terminal_path: str | None = None
    mt5_login: int | None = None
    mt5_password: str | None = None
    mt5_server: str | None = None
    mt5_deviation: int = 15
    mt5_magic: int = 560001

    # Micro-capital profile: percentage sizing, single concurrent position.
    risk_per_trade: float = 0.005
    max_daily_loss: float = 0.02
    max_weekly_loss: float = 0.05
    max_drawdown: float = 0.10
    max_open_positions: int = 1
    max_correlated_positions: int = 1

    fish_audio_model: str = "s2.1-pro"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
