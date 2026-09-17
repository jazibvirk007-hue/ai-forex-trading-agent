from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    risk_per_trade: float = 0.005
    max_daily_loss: float = 0.02
    max_weekly_loss: float = 0.05
    max_drawdown: float = 0.10
    max_open_positions: int = 3
    max_correlated_positions: int = 2


@dataclass(frozen=True)
class AccountState:
    equity: float
    start_of_day_equity: float
    start_of_week_equity: float
    peak_equity: float
    open_positions: int
    correlated_positions: int


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    units: float = 0.0


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def position_units(self, equity: float, stop_distance_price: float, value_per_price_unit: float) -> float:
        if equity <= 0 or stop_distance_price <= 0 or value_per_price_unit <= 0:
            raise ValueError("equity, stop distance and value per price unit must be positive")
        risk_cash = equity * self.limits.risk_per_trade
        return risk_cash / (stop_distance_price * value_per_price_unit)

    def check(self, account: AccountState, stop_distance_price: float, value_per_price_unit: float) -> RiskDecision:
        if account.equity <= 0:
            return RiskDecision(False, "non-positive equity")
        if account.open_positions >= self.limits.max_open_positions:
            return RiskDecision(False, "maximum open positions reached")
        if account.correlated_positions >= self.limits.max_correlated_positions:
            return RiskDecision(False, "correlation limit reached")

        daily_loss = max(0.0, 1 - account.equity / account.start_of_day_equity)
        weekly_loss = max(0.0, 1 - account.equity / account.start_of_week_equity)
        drawdown = max(0.0, 1 - account.equity / account.peak_equity)
        if daily_loss >= self.limits.max_daily_loss:
            return RiskDecision(False, "daily loss limit reached")
        if weekly_loss >= self.limits.max_weekly_loss:
            return RiskDecision(False, "weekly loss limit reached")
        if drawdown >= self.limits.max_drawdown:
            return RiskDecision(False, "maximum drawdown reached; trading halted")

        units = self.position_units(account.equity, stop_distance_price, value_per_price_unit)
        return RiskDecision(True, "approved", units)
